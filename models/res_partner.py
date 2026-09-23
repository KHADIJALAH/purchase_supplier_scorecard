# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html)

from odoo import api, fields, models
from odoo.tools.float_utils import float_compare


class ResPartner(models.Model):
    """Extend res.partner with automatic supplier scorecard fields.

    The weighting fields used to compute the global score
    (``supplier_scorecard_punctuality_weight`` and
    ``supplier_scorecard_invoice_weight``) are defined on ``res.company``
    in ``res_config_settings.py`` and exposed in Settings.
    """
    _inherit = 'res.partner'

    # Ranking thresholds are business decisions, not user-configurable:
    # only the score weights are exposed in Settings, per functional spec.
    RANKING_THRESHOLD_A = 80.0
    RANKING_THRESHOLD_B = 50.0

    supplier_picking_ids = fields.One2many(
        comodel_name='stock.picking',
        inverse_name='partner_id',
        string='Incoming Receipts',
        domain=[('picking_type_id.code', '=', 'incoming')],
        help='Incoming transfers for which this partner is the vendor. '
             'Used to compute the on-time delivery score.',
    )
    supplier_purchase_order_ids = fields.One2many(
        comodel_name='purchase.order',
        inverse_name='partner_id',
        string='Confirmed Purchase Orders',
        domain=[('state', 'in', ['purchase', 'done'])],
        help='Confirmed purchase orders for this vendor. Used to compute '
             'the invoice compliance score.',
    )
    supplier_evaluation_ids = fields.One2many(
        comodel_name='purchase.supplier.evaluation',
        inverse_name='partner_id',
        string='Supplier Evaluations',
    )
    supplier_punctuality_score = fields.Float(
        string='On-Time Delivery Score (%)',
        compute='_compute_supplier_punctuality_score',
        store=True,
        readonly=True,
        digits=(5, 2),
        help='Percentage of done incoming receipts for this vendor that '
             'were completed on or before their scheduled date.',
    )
    supplier_invoice_compliance_score = fields.Float(
        string='Invoice Compliance Score (%)',
        compute='_compute_supplier_invoice_compliance_score',
        store=True,
        readonly=True,
        digits=(5, 2),
        help='Percentage of vendor bills whose untaxed amount matches the '
             'untaxed amount of their purchase order, without discrepancy.',
    )
    supplier_global_score = fields.Float(
        string='Global Supplier Score (%)',
        compute='_compute_supplier_global_score',
        store=True,
        readonly=True,
        digits=(5, 2),
        help='Weighted average of the on-time delivery and invoice '
             'compliance scores. Weights are configurable in Settings.',
    )
    supplier_ranking = fields.Selection(
        selection=[
            ('a', 'A'),
            ('b', 'B'),
            ('c', 'C'),
            ('none', 'Not Evaluated'),
        ],
        string='Supplier Ranking',
        compute='_compute_supplier_ranking',
        store=True,
        readonly=True,
        default='none',
        help='Automatic ranking derived from the global supplier score. '
             '"Not Evaluated" is used when no receipt or invoice data is '
             'available yet.',
    )

    @api.depends(
        'supplier_picking_ids.state',
        'supplier_picking_ids.scheduled_date',
        'supplier_picking_ids.date_done',
    )
    def _compute_supplier_punctuality_score(self):
        """Compute the on-time delivery score for each partner.

        Only done incoming transfers are taken into account. A receipt is
        considered on time when it was completed on or before its
        scheduled date.
        """
        for partner in self:
            done_pickings = partner.supplier_picking_ids.filtered(
                lambda picking: picking.state == 'done' and picking.date_done
            )
            if not done_pickings:
                partner.supplier_punctuality_score = 0.0
                continue
            on_time_count = len(done_pickings.filtered(
                lambda picking: picking.date_done <= picking.scheduled_date
            ))
            partner.supplier_punctuality_score = (
                on_time_count / len(done_pickings) * 100.0
            )

    @api.depends(
        'supplier_purchase_order_ids.amount_untaxed',
        'supplier_purchase_order_ids.invoice_ids.state',
        'supplier_purchase_order_ids.invoice_ids.amount_untaxed',
    )
    def _compute_supplier_invoice_compliance_score(self):
        """Compute the invoice compliance score for each partner.

        A purchase order is considered compliant when the sum of the
        untaxed amounts of its posted vendor bills matches the order's own
        untaxed amount (rounding tolerance based on the order currency).
        Orders without any posted vendor bill yet are excluded, since they
        cannot be judged compliant or not.
        """
        for partner in self:
            evaluated_orders = partner.env['purchase.order']
            compliant_orders = partner.env['purchase.order']
            for order in partner.supplier_purchase_order_ids:
                posted_bills = order.invoice_ids.filtered(
                    lambda move: move.state == 'posted'
                )
                if not posted_bills:
                    continue
                evaluated_orders |= order
                billed_amount = sum(posted_bills.mapped('amount_untaxed'))
                precision_rounding = order.currency_id.rounding
                if float_compare(
                    billed_amount,
                    order.amount_untaxed,
                    precision_rounding=precision_rounding,
                ) == 0:
                    compliant_orders |= order
            if not evaluated_orders:
                partner.supplier_invoice_compliance_score = 0.0
                continue
            partner.supplier_invoice_compliance_score = (
                len(compliant_orders) / len(evaluated_orders) * 100.0
            )

    @api.depends(
        'supplier_punctuality_score',
        'supplier_invoice_compliance_score',
        'company_id.supplier_scorecard_punctuality_weight',
        'company_id.supplier_scorecard_invoice_weight',
    )
    def _compute_supplier_global_score(self):
        """Compute the weighted global score for each partner.

        Weights are read from the current company when the partner has no
        specific company set, matching Odoo's multi-company defaults.
        """
        for partner in self:
            company = partner.company_id or partner.env.company
            punctuality_weight = company.supplier_scorecard_punctuality_weight
            invoice_weight = company.supplier_scorecard_invoice_weight
            total_weight = punctuality_weight + invoice_weight
            if not total_weight:
                partner.supplier_global_score = 0.0
                continue
            partner.supplier_global_score = (
                partner.supplier_punctuality_score * punctuality_weight
                + partner.supplier_invoice_compliance_score * invoice_weight
            ) / total_weight

    @api.depends(
        'supplier_global_score',
        'supplier_picking_ids.state',
        'supplier_purchase_order_ids.invoice_ids.state',
    )
    def _compute_supplier_ranking(self):
        """Derive the A / B / C / Not Evaluated ranking from the global score."""
        for partner in self:
            has_done_picking = bool(partner.supplier_picking_ids.filtered(
                lambda picking: picking.state == 'done'
            ))
            has_posted_bill = bool(partner.supplier_purchase_order_ids.invoice_ids.filtered(
                lambda move: move.state == 'posted'
            ))
            if not has_done_picking and not has_posted_bill:
                partner.supplier_ranking = 'none'
            elif partner.supplier_global_score >= self.RANKING_THRESHOLD_A:
                partner.supplier_ranking = 'a'
            elif partner.supplier_global_score >= self.RANKING_THRESHOLD_B:
                partner.supplier_ranking = 'b'
            else:
                partner.supplier_ranking = 'c'

    @api.model
    def _cron_recompute_supplier_scores(self):
        """Force a full recomputation of the supplier scorecard fields.

        Scheduled nightly as a safety net: receipts, vendor bills and
        purchase orders are updated by several different flows (manual
        entry, imports, other modules), and a stored computed field only
        refreshes reliably when every one of those flows touches a field
        listed in its dependencies.
        """
        suppliers = self.search([('supplier_rank', '>', 0)])
        suppliers._compute_supplier_punctuality_score()
        suppliers._compute_supplier_invoice_compliance_score()
        suppliers._compute_supplier_global_score()
        suppliers._compute_supplier_ranking()
