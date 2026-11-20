# DoniaLink App (`donialink_app`)

One installable phone app (PWA) per database, served by Odoo at `/dl/app`: inbox and Web Push, screens added by
other modules, a business summary and an admin dashboard (DoniaLink App > Dashboard, App Managers).

## Sending a notification

```python
env['donialink.app.message'].send(
    kind='report',                 # a donialink.app.kind code (or record); optional with users=
    title='Weekly report', body='<p>Text or HTML</p>',
    users=None,                    # res.users; None = the kind's recipients
    company=company,               # people without access to it are left out
    file=('report.pdf', pdf_bytes, 'application/pdf'), url='#screen-key' or '/odoo/...' or 'https://...',
    sender='DoniaLink', origin='my_module', push=None)   # push: True/False forces, None = the kind's setting
```

Recipients of a kind = the people chosen + the members of its recipient groups + the people with a role that
includes it, active, with access to the company, minus those who switched it off.

## Kinds (data XML)

```xml
<record id="kind_my_alert" model="donialink.app.kind">
    <field name="code">my_alert</field>
    <field name="name">My alert</field>
    <field name="icon">alert</field>   <!-- bell, report, cash, receipt, chart, alert, box, card, info -->
    <field name="recipient_group_ids" eval="[(4, ref('my_module.group_x'))]"/>
</record>
```

## Screens

A tile on the app's home page: a JS screen registered with `DLApp.screen('<key>', {render(el, params, app)})` in the
`donialink_app.assets_app` bundle, or a link (`url`). Visible to everyone when it has no `group_ids` and no
`user_ids`; otherwise to those groups, those people and the people whose role includes the screen.
`requires_model` hides it when a model is missing (soft dependency).

## Roles (data XML)

Presets: `donialink_app.role_owner`, `role_manager`, `role_accountant`, `role_staff` (default for new users).
A role gives groups (added when assigned, taken back when removed unless another role still gives them or the
person had them before), screens, kinds and default companies. Add or extend roles in data:

```xml
<record id="donialink_app.role_owner" model="donialink.app.role">
    <field name="screen_ids" eval="[(4, ref('my_module.screen_x'))]"/>
    <field name="kind_ids" eval="[(4, ref('my_module.kind_my_alert'))]"/>
</record>
```

## Admin dashboard cards

Simple card (Python):

```python
class DonialinkAppAdmin(models.AbstractModel):
    _inherit = 'donialink.app.admin'

    def _dl_app_admin_sections(self):
        return super()._dl_app_admin_sections() + [{
            'key': 'my_card', 'title': _('My card'), 'sequence': 30,
            'numbers': [{'label': _('Waiting'), 'value': 3, 'warn': True}],
            'action': 'my_module.my_action', 'button': _('Open'),
        }]
```

Richer card (JS): register an OWL component under the same key; it gets `section` and `reload` props.

```js
import { registry } from "@web/core/registry";
registry.category("donialink_app.admin_sections").add("my_card", MyCardComponent);
```

## Business summary

`donialink.app.summary` reads donialink_agent's read tools in process (soft dependency) for one of the person's
companies. Groups: *See business summary* and *See finance (profit, bills)*.

## Tasks

Light employee tasks (portal staff included): "My tasks" and "Team tasks" (group *Manage tasks*) in the app,
Tasks in the backend, kinds `task_assigned`, `task_due` (reminder and overdue, hourly cron) and `task_done`.
Create one from code:

```python
env['donialink.app.task'].create_for(
    accountant_users, 'Explain the cash difference of POS/0042', description='Short of 25,000',
    deadline=fields.Datetime.now() + timedelta(days=1), priority='1', lines=['Count again', 'Ask the cashier'],
    photo_required=False, origin='expense_cash_control', res_model='pos.session', res_id=session.id,
    repeat='none')   # or 'daily', or 'weekly' with repeat_weekdays='0,3' (0 = Monday)
```

Connector tools (donialink_agent): `app_create_task`, `app_list_tasks`.
