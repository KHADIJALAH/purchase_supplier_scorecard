# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html)

from datetime import timedelta

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSupplierScorecard(AccountTestInvoicingCommon):
    """Unit tests for the automatic and manual supplier scorecard.

    Inherits from AccountTestInvoicingCommon (itself a TransactionCase) to
    get a company with a working chart of accounts, required to post
    vendor bills. Every test creates its own supplier, product and
    documents rather than relying on demo data.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supplier = cls.env['res.partner'].create({
            'name': 'Test Scorecard Supplier',
            'supplier_rank': 1,
            # Scoped to the test company so that changes to that company's
            # scorecard weights (see test_ranking_and_global_score_weighting)
            # trigger a recompute through the company_id dependency.
            'company_id': cls.env.company.id,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Scorecard Test Product',
            'type': 'consu',
            'purchase_method': 'purchase',
        })

    def _create_confirmed_order(self, quantity=1.0, price_unit=100.0):
        """Create and confirm a purchase order with a single line."""
        order = self.env['purchase.order'].create({
            'partner_id': self.supplier.id,
            'order_line': [Command.create({
                'product_id': self.product.id,
                'name': self.product.name,
                'product_qty': quantity,
                'product_uom': self.product.uom_po_id.id,
                'price_unit': price_unit,
                'date_planned': fields.Datetime.now(),
            })],
        })
        order.button_confirm()
        return order

    def test_punctuality_score(self):
        """The on-time delivery score reflects the share of receipts done on or before their scheduled date."""
        on_time_order = self._create_confirmed_order()
        on_time_picking = on_time_order.picking_ids
        on_time_picking.scheduled_date = fields.Datetime.now() + timedelta(days=1)
        on_time_picking.button_validate()

        late_order = self._create_confirmed_order()
        late_picking = late_order.picking_ids
        late_picking.scheduled_date = fields.Datetime.now() - timedelta(days=1)
        late_picking.button_validate()

        self.assertEqual(self.supplier.supplier_punctuality_score, 50.0)

    def test_invoice_compliance_score(self):
        """The invoice compliance score reflects the share of bills matching their purchase order amount."""
        compliant_order = self._create_confirmed_order(quantity=1.0, price_unit=100.0)
        compliant_order.action_create_invoice()
        compliant_invoice = compliant_order.invoice_ids
        compliant_invoice.invoice_date = fields.Date.today()
        compliant_invoice.action_post()

        mismatched_order = self._create_confirmed_order(quantity=1.0, price_unit=100.0)
        mismatched_order.action_create_invoice()
        mismatched_invoice = mismatched_order.invoice_ids
        mismatched_invoice.invoice_line_ids.quantity = 2.0
        mismatched_invoice.invoice_date = fields.Date.today()
        mismatched_invoice.action_post()

        self.assertEqual(self.supplier.supplier_invoice_compliance_score, 50.0)

    def test_ranking_not_evaluated_without_data(self):
        """A supplier with no receipt and no posted bill is ranked as Not Evaluated."""
        untouched_supplier = self.env['res.partner'].create({
            'name': 'Untouched Supplier',
            'supplier_rank': 1,
        })
        self.assertEqual(untouched_supplier.supplier_ranking, 'none')

    def test_ranking_and_global_score_weighting(self):
        """The global score follows the configured weights and drives the ranking."""
        order = self._create_confirmed_order(quantity=1.0, price_unit=100.0)
        picking = order.picking_ids
        picking.scheduled_date = fields.Datetime.now() + timedelta(days=1)
        picking.button_validate()

        order.action_create_invoice()
        invoice = order.invoice_ids
        invoice.invoice_line_ids.quantity = 2.0
        invoice.invoice_date = fields.Date.today()
        invoice.action_post()

        self.assertEqual(self.supplier.supplier_punctuality_score, 100.0)
        self.assertEqual(self.supplier.supplier_invoice_compliance_score, 0.0)

        self.env.company.supplier_scorecard_punctuality_weight = 100.0
        self.env.company.supplier_scorecard_invoice_weight = 0.0
        self.assertEqual(self.supplier.supplier_global_score, 100.0)
        self.assertEqual(self.supplier.supplier_ranking, 'a')

        self.env.company.supplier_scorecard_punctuality_weight = 0.0
        self.env.company.supplier_scorecard_invoice_weight = 100.0
        self.assertEqual(self.supplier.supplier_global_score, 0.0)
        self.assertEqual(self.supplier.supplier_ranking, 'c')

    def test_evaluation_unique_validated_period_constraint(self):
        """Two validated evaluations cannot coexist for the same supplier and period.

        Uses sudo() since this test targets the model constraint, not
        access rights (covered separately by test_access_rights).
        """
        period_start = fields.Date.today()
        period_end = fields.Date.today() + timedelta(days=30)
        Evaluation = self.env['purchase.supplier.evaluation'].sudo()
        first_evaluation = Evaluation.create({
            'partner_id': self.supplier.id,
            'period_start': period_start,
            'period_end': period_end,
            'quality_note': 4.0,
            'responsiveness_note': 4.0,
            'price_note': 4.0,
        })
        first_evaluation.action_validate()

        second_evaluation = Evaluation.create({
            'partner_id': self.supplier.id,
            'period_start': period_start,
            'period_end': period_end,
            'quality_note': 2.0,
            'responsiveness_note': 2.0,
            'price_note': 2.0,
        })
        with self.assertRaises(ValidationError):
            second_evaluation.action_validate()

    def test_access_rights(self):
        """Only users in the Supplier Evaluation group can access evaluations."""
        evaluator = new_test_user(
            self.env,
            login='scorecard_evaluator',
            groups='purchase_supplier_scorecard.group_supplier_evaluation',
        )
        buyer_without_evaluation_group = new_test_user(
            self.env,
            login='scorecard_buyer',
            groups='purchase.group_purchase_user',
        )
        evaluation = self.env['purchase.supplier.evaluation'].sudo().create({
            'partner_id': self.supplier.id,
            'period_start': fields.Date.today(),
            'period_end': fields.Date.today() + timedelta(days=30),
        })

        evaluation.with_user(evaluator).read(['quality_note'])

        with self.assertRaises(AccessError):
            evaluation.with_user(buyer_without_evaluation_group).read(['quality_note'])
