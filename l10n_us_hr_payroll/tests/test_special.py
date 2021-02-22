from .common import TestUsPayslip, process_payslip


class TestSpecial(TestUsPayslip):
    def test_semi_monthly(self):
        salary = 80000.0
        employee = self._createEmployee()
        # so the schedule_pay is now on the Structure...
        contract = self._createContract(employee, wage=salary, schedule_pay='semi-monthly')
        payslip = self._createPayslip(employee, '2020-01-01', '2020-01-14')
        payslip.compute_sheet()

    def test_payslip_sum_behavior(self):
        us_structure = self.env.ref('l10n_us_hr_payroll.structure_type_employee')
        rule_category_comp = self.env.ref('hr_payroll.COMP')
        test_rule_category = self.env['hr.salary.rule.category'].create({
            'name': 'Test Sum Behavior',
            'code': 'test_sum_behavior',
            'parent_id': rule_category_comp.id,
        })
        test_rule = self.env['hr.salary.rule'].create({
            'sequence': 450,
            'category_id': test_rule_category.id,
            'name': 'Test Sum Behavior',
            'code': 'test_sum_behavior',
            'condition_select': 'python',
            'condition_python': 'result = 1',
            'amount_select': 'code',
            'amount_python_compute': '''
ytd_category = payslip.sum_category('test_sum_behavior', '2021-01-01', '2022-01-01')
ytd_rule = payslip.sum('test_sum_behavior', '2021-01-01', '2022-01-01')
result = 0.0
if ytd_category != ytd_rule:
  # error
  result = -1.0
elif ytd_rule == 0.0:
  # first payslip in period
  result = 1.0
'''
        })
        us_structure.write({'rule_ids': [(4, test_rule.id, 0)]})

        salary = 80000.0
        employee = self._createEmployee()
        contract = self._createContract(employee, wage=salary, schedule_pay='bi-weekly')
        payslip = self._createPayslip(employee, '2020-12-30', '2021-01-12')
        payslip.compute_sheet()
        cats = self._getCategories(payslip)
        self.assertEqual(cats['test_sum_behavior'], 1.0)
        process_payslip(payslip)

        # Basic date_from behavior.
        self.env['ir.config_parameter'].set_param('hr_payroll.payslip.sum_behavior', 'date_from')
        # The the date_from on the last payslip will not be found
        payslip = self._createPayslip(employee, '2021-01-13', '2021-01-27')
        payslip.compute_sheet()
        cats = self._getCategories(payslip)
        self.assertEqual(cats['test_sum_behavior'], 1.0)

        # date_to behavior.
        self.env['ir.config_parameter'].set_param('hr_payroll.payslip.sum_behavior', 'date_to')
        # The date_to on the last payslip is found
        payslip = self._createPayslip(employee, '2021-01-13', '2021-01-27')
        payslip.compute_sheet()
        cats = self._getCategories(payslip)
        self.assertEqual(cats['test_sum_behavior'], 0.0)

    def test_recursive_salary_rule_category(self):
        self.debug = True
        # In this scenario, you are in rule code that will check for the category
        # and a subcategory will also
        alw_category = self.env.ref('hr_payroll.ALW')
        ded_category = self.env.ref('hr_payroll.DED')
        test_category = self.env['hr.salary.rule.category'].create({
            'name': 'Special ALW',
            'code': 'ALW_SPECIAL_RECURSIVE',
            'parent_id': alw_category.id,
        })
        test_special_alw = self.env['hr.salary.rule'].create({
            'name': 'Flat amount 200',
            'code': 'ALW_SPECIAL_RECURSIVE',
            'category_id': test_category.id,
            'condition_select': 'none',
            'amount_select': 'fix',
            'amount_fix': 200.0,
        })
        test_recursion = self.env['hr.salary.rule'].create({
            'name': 'Actual Test Behavior',
            'code': 'RECURSION_TEST',
            'category_id': ded_category.id,
            'condition_select': 'none',
            'amount_select': 'code',
            'amount_python_compute': """
# this rule will always be the total of the ALW category and YTD ALW category
result = categories.ALW
year = payslip.dict.get_year()
result += payslip.sum_category('ALW', str(year) + '-01-01', str(year+1) + '-01-01')
            """,
            'sequence': 101,
        })
        struct = self.env.ref('l10n_us_hr_payroll.structure_type_employee')
        struct.rule_ids = test_special_alw + test_recursion

        salary = 80000.0
        employee = self._createEmployee()
        contract = self._createContract(employee, wage=salary, schedule_pay='bi-weekly')
        payslip = self._createPayslip(employee, '2021-01-01', '2021-01-14')
        payslip.compute_sheet()
        cats = self._getCategories(payslip)
        rules = self._getRules(payslip)
        self.assertEqual(rules['RECURSION_TEST'], 200.0)
        process_payslip(payslip)

        payslip = self._createPayslip(employee, '2021-01-15', '2021-01-27')
        payslip.compute_sheet()
        cats = self._getCategories(payslip)
        rules = self._getRules(payslip)
        # two hundred is in the YTD ALW
        self.assertEqual(rules['RECURSION_TEST'], 200.0 + 200.0)
