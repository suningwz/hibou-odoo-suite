import suds
from odoo.addons.delivery_fedex.models import fedex_request
from pprint import pformat
import logging
_logger = logging.getLogger(__name__)

STATECODE_REQUIRED_COUNTRIES = fedex_request.STATECODE_REQUIRED_COUNTRIES


def sanitize_name(name):
    if isinstance(name, str):
        return name.replace('[', '').replace(']', '')
    return 'Unknown'


class FedexRequest(fedex_request.FedexRequest):
    _transit_days = {
        'ONE_DAYS': 1,
        'ONE_DAY': 1,
        'TWO_DAYS': 2,
        'THREE_DAYS': 3,
        'FOUR_DAYS': 4,
        'FIVE_DAYS': 5,
        'SIX_DAYS': 6,
        'SEVEN_DAYS': 7,
        'EIGHT_DAYS': 8,
        'NINE_DAYS': 9,
        'TEN_DAYS': 10,
    }

    _service_transit_days = {
        'FEDEX_2_DAY': 2,
        'FEDEX_2_DAY_AM': 2,
        'FIRST_OVERNIGHT': 1,
        'PRIORITY_OVERNIGHT': 1,
        'STANDARD_OVERNIGHT': 1,
    }

    def set_recipient(self, recipient_partner, attn=None, residential=False):
        """
        Adds ATTN: and sanitizes against known 'illegal' common characters in names.
        :param recipient_partner: default
        :param attn: NEW add to contact name as an ' ATTN: $attn'
        :param residential: NEW allow ground home delivery
        :return:
        """
        Contact = self.client.factory.create('Contact')
        if recipient_partner.is_company:
            Contact.PersonName = ''
            Contact.CompanyName = sanitize_name(recipient_partner.name)
        elif recipient_partner.name == recipient_partner.parent_id.name:
            Contact.PersonName = recipient_partner.name
            Contact.CompanyName = ''
        else:
            Contact.PersonName = sanitize_name(recipient_partner.name)
            Contact.CompanyName = sanitize_name(recipient_partner.parent_id.name or '')

        if attn:
            Contact.PersonName = Contact.PersonName + ' ATTN: ' + str(attn)

        Contact.PhoneNumber = recipient_partner.phone or ''

        Address = self.client.factory.create('Address')
        Address.StreetLines = [recipient_partner.street or '', recipient_partner.street2 or '']
        Address.City = recipient_partner.city or ''
        if recipient_partner.country_id.code in STATECODE_REQUIRED_COUNTRIES:
            Address.StateOrProvinceCode = recipient_partner.state_id.code or ''
        else:
            Address.StateOrProvinceCode = ''
        Address.PostalCode = recipient_partner.zip or ''
        Address.CountryCode = recipient_partner.country_id.code or ''

        if residential:
            Address.Residential = True

        self.RequestedShipment.Recipient.Contact = Contact
        self.RequestedShipment.Recipient.Address = Address

    def add_package(self, weight_value, sequence_number=False, mode='shipping', ref=False, insurance=False):
        """
        Adds ref type of object to include.
        :param weight_value: default
        :param sequence_number: default
        :param mode: default
        :param ref: NEW add CUSTOMER_REFERENCE object
        :param insurance: NEW add Insurance amount
        :return:
        """
        package = self.client.factory.create('RequestedPackageLineItem')
        package_weight = self.client.factory.create('Weight')
        package_weight.Value = weight_value
        package_weight.Units = self.RequestedShipment.TotalWeight.Units

        if ref:
            customer_ref = self.client.factory.create('CustomerReference')
            customer_ref.CustomerReferenceType = 'CUSTOMER_REFERENCE'
            customer_ref.Value = str(ref)
            package.CustomerReferences.append(customer_ref)

        if insurance:
            insured = self.client.factory.create('Money')
            insured.Amount = insurance
            # TODO at some point someone might need currency here
            insured.Currency = 'USD'
            package.InsuredValue = insured

        package.PhysicalPackaging = 'BOX'
        package.Weight = package_weight
        if mode == 'rating':
            package.GroupPackageCount = 1
        if sequence_number:
            package.SequenceNumber = sequence_number
        else:
            self.hasOnePackage = True

        if mode == 'rating':
            self.RequestedShipment.RequestedPackageLineItems.append(package)
        else:
            self.RequestedShipment.RequestedPackageLineItems = package

    def shipping_charges_payment(self, shipping_charges_payment_account, third_party=False):
        """
        Allow 'shipping_charges_payment_account' to be considered 'third_party'
        :param shipping_charges_payment_account: default
        :param third_party: NEW add to indicate that the 'shipping_charges_payment_account' is third party.
        :return:
        """
        self.RequestedShipment.ShippingChargesPayment.PaymentType = 'SENDER' if not third_party else 'THIRD_PARTY'
        Payor = self.client.factory.create('Payor')
        Payor.ResponsibleParty.AccountNumber = shipping_charges_payment_account
        self.RequestedShipment.ShippingChargesPayment.Payor = Payor

    # Rating stuff

    def rate(self, date_planned=None):
        """
        Response will contain 'transit_days' key with number of days.
        :param date_planned: Planned Outgoing shipment. Used to have FedEx tell us how long it will take for the package to arrive.
        :return:
        """
        formatted_response = {'price': {}}
        del self.ClientDetail.Region

        if date_planned:
            # though Fedex sends BACK timestamps like `2020-01-01 00:00:00` they EXPECT `2020-01-01T00:00:00`
            self.RequestedShipment.ShipTimestamp = date_planned.replace(' ', 'T')

        try:
            self.response = self.client.service.getRates(WebAuthenticationDetail=self.WebAuthenticationDetail,
                                                         ClientDetail=self.ClientDetail,
                                                         TransactionDetail=self.TransactionDetail,
                                                         Version=self.VersionId,
                                                         RequestedShipment=self.RequestedShipment,
                                                         ReturnTransitAndCommit=True)  # New ReturnTransitAndCommit for CommitDetails in response
            if (self.response.HighestSeverity != 'ERROR' and self.response.HighestSeverity != 'FAILURE'):
                for rating in self.response.RateReplyDetails[0].RatedShipmentDetails:
                    formatted_response['price'][rating.ShipmentRateDetail.TotalNetFedExCharge.Currency] = rating.ShipmentRateDetail.TotalNetFedExCharge.Amount
                if len(self.response.RateReplyDetails[0].RatedShipmentDetails) == 1:
                    if 'CurrencyExchangeRate' in self.response.RateReplyDetails[0].RatedShipmentDetails[0].ShipmentRateDetail:
                        formatted_response['price'][self.response.RateReplyDetails[0].RatedShipmentDetails[0].ShipmentRateDetail.CurrencyExchangeRate.FromCurrency] = self.response.RateReplyDetails[0].RatedShipmentDetails[0].ShipmentRateDetail.TotalNetFedExCharge.Amount / self.response.RateReplyDetails[0].RatedShipmentDetails[0].ShipmentRateDetail.CurrencyExchangeRate.Rate

                # Hibou Delivery Planning
                if hasattr(self.response.RateReplyDetails[0], 'DeliveryTimestamp') and self.response.RateReplyDetails[0].DeliveryTimestamp:
                    formatted_response['date_delivered'] = self.response.RateReplyDetails[0].DeliveryTimestamp
                elif hasattr(self.response.RateReplyDetails[0].CommitDetails[0], 'CommitTimestamp'):
                    formatted_response['date_delivered'] = self.response.RateReplyDetails[0].CommitDetails[0].CommitTimestamp
                    formatted_response['transit_days'] = self._service_transit_days.get(self.response.RateReplyDetails[0].CommitDetails[0].ServiceType, 0)
                elif hasattr(self.response.RateReplyDetails[0].CommitDetails[0], 'TransitTime'):
                    transit_days = self.response.RateReplyDetails[0].CommitDetails[0].TransitTime
                    transit_days = self._transit_days.get(transit_days, 0)
                    formatted_response['transit_days'] = transit_days

            else:
                errors_message = '\n'.join([("%s: %s" % (n.Code, n.Message)) for n in self.response.Notifications if (n.Severity == 'ERROR' or n.Severity == 'FAILURE')])
                formatted_response['errors_message'] = errors_message

            if any([n.Severity == 'WARNING' for n in self.response.Notifications]):
                warnings_message = '\n'.join([("%s: %s" % (n.Code, n.Message)) for n in self.response.Notifications if n.Severity == 'WARNING'])
                formatted_response['warnings_message'] = warnings_message

        except suds.WebFault as fault:
            formatted_response['errors_message'] = fault
        except IOError:
            formatted_response['errors_message'] = "Fedex Server Not Found"

        return formatted_response
