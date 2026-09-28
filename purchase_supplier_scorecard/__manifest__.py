{
    'name': 'Purchase Supplier Scorecard',
    'version': '18.0.1.0.1',
    'category': 'Inventory/Purchase',
    'summary': 'Automatic and manual supplier performance scoring for the Purchase module',
    'description': """
Purchase Supplier Scorecard
============================

Extends the Purchase module to automatically score suppliers based on
their real performance and lets buyers complement that score with a
periodic manual evaluation.

Key features
------------
* On-time delivery score computed from confirmed incoming receipts.
* Invoice accuracy score computed from vendor bills matched against
  their purchase orders.
* Configurable weighted global score.
* Automatic A / B / C / Not Evaluated ranking.
* Manual periodic evaluation with a draft / validated / closed workflow.
* One validated evaluation per supplier and per period.
* Dedicated security group and multi-company record rules.
* Nightly scheduled recomputation of scores.
""",
    'author': 'Khadija Lahlou',
    'website': 'https://khadija-portfolio-nine.vercel.app/',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': [
        'mail',
        'purchase',
        'purchase_stock',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/purchase_supplier_evaluation_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
