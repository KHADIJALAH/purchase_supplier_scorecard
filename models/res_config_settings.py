# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html)

from odoo import fields, models

DEFAULT_PUNCTUALITY_WEIGHT = 50.0
DEFAULT_INVOICE_WEIGHT = 50.0


class ResCompany(models.Model):
    """Store the supplier scorecard weighting configuration per company."""
    _inherit = 'res.company'

    supplier_scorecard_punctuality_weight = fields.Float(
        string='On-Time Delivery Weight',
        default=DEFAULT_PUNCTUALITY_WEIGHT,
        help='Relative weight of the on-time delivery score in the global '
             'supplier score. Weights do not need to sum to 100: they are '
             'normalized automatically.',
    )
    supplier_scorecard_invoice_weight = fields.Float(
        string='Invoice Compliance Weight',
        default=DEFAULT_INVOICE_WEIGHT,
        help='Relative weight of the invoice compliance score in the '
             'global supplier score. Weights do not need to sum to 100: '
             'they are normalized automatically.',
    )


class ResConfigSettings(models.TransientModel):
    """Expose the supplier scorecard weights in the Purchase settings."""
    _inherit = 'res.config.settings'

    supplier_scorecard_punctuality_weight = fields.Float(
        related='company_id.supplier_scorecard_punctuality_weight',
        string='On-Time Delivery Weight',
        readonly=False,
    )
    supplier_scorecard_invoice_weight = fields.Float(
        related='company_id.supplier_scorecard_invoice_weight',
        string='Invoice Compliance Weight',
        readonly=False,
    )
