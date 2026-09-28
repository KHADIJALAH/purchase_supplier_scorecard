# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html)

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

MANUAL_NOTE_MIN = 0.0
MANUAL_NOTE_MAX = 5.0


class PurchaseSupplierEvaluation(models.Model):
    """Manual, periodic evaluation of a supplier by a buyer.

    Complements the automatic scorecard fields on res.partner with
    qualitative criteria (quality, responsiveness, price) that cannot be
    derived from transactional data alone.
    """
    _name = 'purchase.supplier.evaluation'
    _inherit = ['mail.thread']
    _description = 'Purchase Supplier Evaluation'
    _order = 'period_start desc, id desc'

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Supplier',
        required=True,
        domain=[('supplier_rank', '>', 0)],
        tracking=True,
    )
    period_start = fields.Date(string='Period Start', required=True, tracking=True)
    period_end = fields.Date(string='Period End', required=True, tracking=True)
    quality_note = fields.Float(
        string='Quality',
        help='Manual quality rating from 0 (very poor) to 5 (excellent).',
    )
    responsiveness_note = fields.Float(
        string='Responsiveness',
        help='Manual responsiveness rating from 0 (very poor) to 5 (excellent).',
    )
    price_note = fields.Float(
        string='Price Competitiveness',
        help='Manual price rating from 0 (very poor) to 5 (excellent).',
    )
    manual_global_note = fields.Float(
        string='Manual Global Note',
        compute='_compute_manual_global_note',
        store=True,
        readonly=True,
        help='Average of the quality, responsiveness and price ratings.',
    )
    partner_ranking = fields.Selection(
        related='partner_id.supplier_ranking',
        string='Supplier Ranking',
        store=True,
    )
    comment = fields.Text(string='Comment')
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('validated', 'Validated'),
            ('closed', 'Closed'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    name = fields.Char(compute='_compute_name', store=True)

    @api.depends('partner_id.name', 'period_start', 'period_end')
    def _compute_name(self):
        """Build a human-readable label combining the supplier and the period."""
        for evaluation in self:
            if evaluation.partner_id and evaluation.period_start and evaluation.period_end:
                evaluation.name = _(
                    '%(partner)s (%(start)s - %(end)s)',
                    partner=evaluation.partner_id.name,
                    start=evaluation.period_start,
                    end=evaluation.period_end,
                )
            else:
                evaluation.name = _('New Evaluation')

    @api.depends('quality_note', 'responsiveness_note', 'price_note')
    def _compute_manual_global_note(self):
        """Average the three manual rating criteria into a single note."""
        for evaluation in self:
            evaluation.manual_global_note = (
                evaluation.quality_note
                + evaluation.responsiveness_note
                + evaluation.price_note
            ) / 3.0

    @api.constrains('quality_note', 'responsiveness_note', 'price_note')
    def _check_manual_notes_range(self):
        """Ensure manual ratings stay within the 0 to 5 scale."""
        for evaluation in self:
            notes = (
                evaluation.quality_note,
                evaluation.responsiveness_note,
                evaluation.price_note,
            )
            if any(note < MANUAL_NOTE_MIN or note > MANUAL_NOTE_MAX for note in notes):
                raise ValidationError(_(
                    'Quality, responsiveness and price ratings must be '
                    'between %(min)s and %(max)s.',
                    min=MANUAL_NOTE_MIN,
                    max=MANUAL_NOTE_MAX,
                ))

    @api.constrains('period_start', 'period_end')
    def _check_period_dates(self):
        """Ensure the evaluation period is a valid, non-inverted date range."""
        for evaluation in self:
            if evaluation.period_start and evaluation.period_end \
                    and evaluation.period_start > evaluation.period_end:
                raise ValidationError(_('The period start date must be before its end date.'))

    @api.constrains('state', 'partner_id', 'period_start', 'period_end', 'company_id')
    def _check_unique_validated_evaluation(self):
        """Enforce a single validated evaluation per supplier and per period.

        Draft or closed evaluations are not restricted, so a buyer can keep
        several drafts and historical closed records for the same period.
        """
        for evaluation in self:
            if evaluation.state != 'validated':
                continue
            domain = [
                ('id', '!=', evaluation.id),
                ('partner_id', '=', evaluation.partner_id.id),
                ('period_start', '=', evaluation.period_start),
                ('period_end', '=', evaluation.period_end),
                ('company_id', '=', evaluation.company_id.id),
                ('state', '=', 'validated'),
            ]
            if self.search_count(domain):
                raise ValidationError(_(
                    'A validated evaluation already exists for %(partner)s '
                    'on this period.',
                    partner=evaluation.partner_id.name,
                ))

    def action_validate(self):
        """Move draft evaluations to the validated state.

        :raises ValidationError: if an evaluation is not currently a draft.
        """
        for evaluation in self:
            if evaluation.state != 'draft':
                raise ValidationError(_('Only a draft evaluation can be validated.'))
        self.write({'state': 'validated'})

    def action_close(self):
        """Close validated evaluations, marking them as final.

        :raises ValidationError: if an evaluation is not currently validated.
        """
        for evaluation in self:
            if evaluation.state != 'validated':
                raise ValidationError(_('Only a validated evaluation can be closed.'))
        self.write({'state': 'closed'})

    def action_reset_to_draft(self):
        """Reset validated evaluations back to draft for correction."""
        for evaluation in self:
            if evaluation.state != 'validated':
                raise ValidationError(_('Only a validated evaluation can be reset to draft.'))
        self.write({'state': 'draft'})
