import suds
from odoo.addons.delivery_ups.models.ups_request import UPSRequest

SUDS_VERSION = suds.__version__


def patched_get_shipping_price(self, shipment_info, packages, shipper, ship_from, ship_to, packaging_type, service_type,
                       saturday_delivery, cod_info, date_planned=False):
    client = self._set_client(self.rate_wsdl, 'Rate', 'RateRequest')

    request = client.factory.create('ns0:RequestType')
    request.RequestOption = 'Rate'

    classification = client.factory.create('ns2:CodeDescriptionType')
    classification.Code = '00'  # Get rates for the shipper account
    classification.Description = 'Get rates for the shipper account'

    namespace = 'ns2'
    shipment = client.factory.create('{}:ShipmentType'.format(namespace))

    # Hibou Delivery
    if date_planned:
        if not isinstance(date_planned, str):
            date_planned = str(date_planned)
        shipment.DeliveryTimeInformation = client.factory.create('{}:TimeInTransitRequestType'.format(namespace))
        shipment.DeliveryTimeInformation.Pickup = client.factory.create('{}:PickupType'.format(namespace))
        shipment.DeliveryTimeInformation.Pickup.Date = date_planned.split(' ')[0]
    # End

    for package in self.set_package_detail(client, packages, packaging_type, namespace, ship_from, ship_to, cod_info):
        shipment.Package.append(package)

    shipment.Shipper.Name = shipper.name or ''
    shipment.Shipper.Address.AddressLine = [shipper.street or '', shipper.street2 or '']
    shipment.Shipper.Address.City = shipper.city or ''
    shipment.Shipper.Address.PostalCode = shipper.zip or ''
    shipment.Shipper.Address.CountryCode = shipper.country_id.code or ''
    if shipper.country_id.code in ('US', 'CA', 'IE'):
        shipment.Shipper.Address.StateProvinceCode = shipper.state_id.code or ''
    shipment.Shipper.ShipperNumber = self.shipper_number or ''
    # shipment.Shipper.Phone.Number = shipper.phone or ''

    shipment.ShipFrom.Name = ship_from.name or ''
    shipment.ShipFrom.Address.AddressLine = [ship_from.street or '', ship_from.street2 or '']
    shipment.ShipFrom.Address.City = ship_from.city or ''
    shipment.ShipFrom.Address.PostalCode = ship_from.zip or ''
    shipment.ShipFrom.Address.CountryCode = ship_from.country_id.code or ''
    if ship_from.country_id.code in ('US', 'CA', 'IE'):
        shipment.ShipFrom.Address.StateProvinceCode = ship_from.state_id.code or ''
    # shipment.ShipFrom.Phone.Number = ship_from.phone or ''

    shipment.ShipTo.Name = ship_to.name or ''
    shipment.ShipTo.Address.AddressLine = [ship_to.street or '', ship_to.street2 or '']
    shipment.ShipTo.Address.City = ship_to.city or ''
    shipment.ShipTo.Address.PostalCode = ship_to.zip or ''
    shipment.ShipTo.Address.CountryCode = ship_to.country_id.code or ''
    if ship_to.country_id.code in ('US', 'CA', 'IE'):
        shipment.ShipTo.Address.StateProvinceCode = ship_to.state_id.code or ''
    # shipment.ShipTo.Phone.Number = ship_to.phone or ''
    if not ship_to.commercial_partner_id.is_company:
        shipment.ShipTo.Address.ResidentialAddressIndicator = suds.null()

    shipment.Service.Code = service_type or ''
    shipment.Service.Description = 'Service Code'
    if service_type == "96":
        shipment.NumOfPieces = int(shipment_info.get('total_qty'))

    if saturday_delivery:
        shipment.ShipmentServiceOptions.SaturdayDeliveryIndicator = saturday_delivery
    else:
        shipment.ShipmentServiceOptions = ''

    shipment.ShipmentRatingOptions.NegotiatedRatesIndicator = 1

    try:
        # Get rate using for provided detail
        response = client.service.ProcessRate(Request=request, CustomerClassification=classification, Shipment=shipment)

        # Check if ProcessRate is not success then return reason for that
        if response.Response.ResponseStatus.Code != "1":
            return self.get_error_message(response.Response.ResponseStatus.Code,
                                          response.Response.ResponseStatus.Description)

        result = {}
        result['currency_code'] = response.RatedShipment[0].TotalCharges.CurrencyCode

        # Some users are qualified to receive negotiated rates
        negotiated_rate = 'NegotiatedRateCharges' in response.RatedShipment[0] and response.RatedShipment[
            0].NegotiatedRateCharges.TotalCharge.MonetaryValue or None

        result['price'] = negotiated_rate or response.RatedShipment[0].TotalCharges.MonetaryValue

        # Hibou Delivery
        if hasattr(response.RatedShipment[0], 'GuaranteedDelivery') and hasattr(response.RatedShipment[0].GuaranteedDelivery, 'BusinessDaysInTransit'):
            result['transit_days'] = int(response.RatedShipment[0].GuaranteedDelivery.BusinessDaysInTransit)
        # End

        return result

    except suds.WebFault as e:
        # childAtPath behaviour is changing at version 0.6
        prefix = ''
        if SUDS_VERSION >= "0.6":
            prefix = '/Envelope/Body/Fault'
        return self.get_error_message(
            e.document.childAtPath(prefix + '/detail/Errors/ErrorDetail/PrimaryErrorCode/Code').getText(),
            e.document.childAtPath(prefix + '/detail/Errors/ErrorDetail/PrimaryErrorCode/Description').getText())
    except IOError as e:
        return self.get_error_message('0', 'UPS Server Not Found:\n%s' % e)


UPSRequest.get_shipping_price = patched_get_shipping_price
