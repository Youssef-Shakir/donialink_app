# -*- coding: utf-8 -*-
{
    'name': 'DoniaLink App',
    'version': '18.0.1.4.1',
    'summary': 'One installable phone app (PWA) for the business: notifications, reports and screens added by '
               'other modules.',
    'description': """
DoniaLink App | تطبيق دنيا لينك
================================

The central phone app of the database, served by Odoo at ``/dl/app`` and installable from the browser
("Add to Home Screen").

* Login with the normal Odoo login (internal or free portal users).
* An inbox of notifications and reports, with Web Push to every phone where the person turned them on.
* A small API so any module can notify people: ``env['donialink.app.message'].send(...)``.
* Kinds of notification, each with its own list of recipients, and a per-person opt-out.
* Screens: other modules add their own tiles and pages to the app (cash box, receipts, …).
* A tile to open the full Odoo for people who edit the database.
* Business summary (sales, expenses, profit, cash differences, bills, stock) per company, live from the DoniaLink
  Agent's tools (soft dependency); groups "See business summary" and "See finance".
* Admin dashboard (DoniaLink App > Dashboard): people, one-step user creation (portal by default), roles, who
  receives and who sees what, activity, broadcast.
* For developers (see README.md): ``send()``, kinds and screens by data XML (recipient groups, people, roles),
  roles by data XML, ``donialink.app.admin._dl_app_admin_sections()`` and the JS registry
  ``donialink_app.admin_sections`` for dashboard cards.

Developed by Yousif Shakir - Donialink | تطوير يوسف شاكر
""",
    'author': 'Donialink, Yousif Shakir',
    'website': 'https://www.donialink.com',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'depends': ['mail', 'portal'],
    'data': [
        'security/security.xml',
        'security/app_task_security.xml',
        'security/ir.model.access.csv',
        'data/app_kind_data.xml',
        'data/app_screen_data.xml',
        'data/app_role_data.xml',
        'data/app_task_data.xml',
        'data/ir_cron_data.xml',
        'views/app_message_views.xml',
        'views/app_kind_views.xml',
        'views/app_screen_views.xml',
        'views/app_role_views.xml',
        'views/app_task_views.xml',
        'views/app_page_templates.xml',
        'views/menus.xml',
    ],
    'assets': {
        # the admin dashboard (backend client action); other modules add cards in
        # registry.category('donialink_app.admin_sections')
        'web.assets_backend': [
            'donialink_app/static/src/admin/**/*',
        ],
        # the phone app: core first; other modules append their screens to this bundle
        'donialink_app.assets_app': [
            'donialink_app/static/src/app/app.css',
            'donialink_app/static/src/app/core.js',
            'donialink_app/static/src/app/screens.js',
            'donialink_app/static/src/app/summary.js',
            'donialink_app/static/src/app/tasks.js',
            'donialink_app/static/src/app/chat.js',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
}
