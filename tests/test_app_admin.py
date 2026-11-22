# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAppAdmin(TransactionCase):
    """Roles, recipients by group / role, screens per person, the admin dashboard and its access."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Role = cls.env['donialink.app.role']
        cls.Admin = cls.env['donialink.app.admin']
        cls.manager = new_test_user(cls.env, 'dl_adm_manager',
                                    groups='base.group_user,donialink_app.group_app_manager,donialink_app.group_finance')
        cls.clerk = new_test_user(cls.env, 'dl_adm_clerk', groups='base.group_user')
        cls.staff = new_test_user(cls.env, 'dl_adm_staff', groups='base.group_portal')
        cls.summary = cls.env.ref('donialink_app.group_summary')
        cls.finance = cls.env.ref('donialink_app.group_finance')
        cls.kind = cls.env['donialink.app.kind'].create({'code': 'dl_adm_test', 'name': 'Admin test kind'})

    def test_presets(self):
        for xmlid in ('role_owner', 'role_manager', 'role_accountant', 'role_staff'):
            self.assertTrue(self.env.ref('donialink_app.%s' % xmlid))
        self.assertTrue(self.env.ref('donialink_app.role_staff').is_default)

    def test_role_grants_and_takes_back_groups(self):
        a = self.Role.create({'name': 'A', 'group_ids': [(6, 0, self.finance.ids)]})
        b = self.Role.create({'name': 'B', 'group_ids': [(6, 0, self.summary.ids)]})
        self.staff.dl_app_role_ids = a | b
        self.assertIn(self.finance, self.staff.groups_id)
        self.assertIn(self.finance, self.staff.dl_app_role_group_ids)
        self.staff.dl_app_role_ids = b
        self.assertNotIn(self.finance, self.staff.groups_id, 'taken back with the role')
        self.assertIn(self.summary, self.staff.groups_id, 'still given by the other role')
        # from the role side too
        a.user_ids = [(4, self.staff.id)]
        self.assertIn(self.finance, self.staff.groups_id)
        a.user_ids = [(3, self.staff.id)]
        self.assertNotIn(self.finance, self.staff.groups_id)

    def test_manual_group_is_kept(self):
        self.clerk.groups_id = [(4, self.finance.id)]
        role = self.Role.create({'name': 'Fin', 'user_type': 'internal', 'group_ids': [(6, 0, self.finance.ids)]})
        self.clerk.dl_app_role_ids = role
        self.clerk.dl_app_role_ids = False
        self.assertIn(self.finance, self.clerk.groups_id, 'a group chosen by hand is not taken back')

    def test_portal_user_can_not_get_internal_groups(self):
        role = self.Role.create({'name': 'Odoo', 'group_ids': [(6, 0, self.env.ref('base.group_system').ids)]})
        with self.assertRaises(UserError):
            self.staff.dl_app_role_ids = role

    def test_recipients_by_group_and_role(self):
        group = self.env['res.groups'].create({'name': 'DL Adm Kitchen', 'users': [(6, 0, self.clerk.ids)]})
        role = self.Role.create({'name': 'Staff X', 'kind_ids': [(6, 0, self.kind.ids)], 'user_ids': [(6, 0, self.staff.ids)]})
        self.kind.recipient_group_ids = group
        self.assertEqual(self.kind._recipients(), self.clerk | self.staff)
        self.kind.muted_user_ids = self.clerk
        self.assertEqual(self.kind._recipients(), self.staff)
        messages = self.env['donialink.app.message'].send(kind='dl_adm_test', title='Hi')
        self.assertEqual(messages.user_id, self.staff, 'send() without users reaches the role members')
        self.assertEqual(role.kind_ids, self.kind)

    def test_screens_per_person_and_role(self):
        screen = self.env['donialink.app.screen'].create({
            'key': 'dl_adm_screen', 'name': 'Secret', 'group_ids': [(6, 0, self.env.ref('base.group_system').ids)]})
        Screen = self.env['donialink.app.screen']
        self.assertNotIn(screen, Screen._for_user(self.staff))
        screen.user_ids = self.staff
        self.assertIn(screen, Screen._for_user(self.staff))
        screen.user_ids = False
        self.Role.create({'name': 'Viewer', 'screen_ids': [(6, 0, screen.ids)], 'user_ids': [(6, 0, self.clerk.ids)]})
        self.assertIn(screen, Screen._for_user(self.clerk))
        self.assertIn(self.env.ref('donialink_app.screen_inbox'), Screen._for_user(self.staff), 'open screens stay open')

    def test_create_user(self):
        admin = self.Admin.with_user(self.manager)
        staff = admin.create_user('Ali Cashier', '07701234567')
        self.assertTrue(staff['password'], 'generated and returned once')
        self.assertEqual(staff['type'], 'portal')
        user = self.env['res.users'].browse(staff['user_id'])
        self.assertTrue(user.share)
        self.assertEqual(user.dl_app_role_ids, self.env.ref('donialink_app.role_staff'), 'the default role')
        manager = admin.create_user('Sara', 'sara.dl', password='Sara-pass-1',
                                    role_ids=[self.env.ref('donialink_app.role_manager').id])
        self.assertFalse(manager['password'])
        self.assertEqual(manager['type'], 'internal')
        self.assertIn(self.finance, self.env['res.users'].browse(manager['user_id']).groups_id)
        with self.assertRaises(UserError):
            admin.create_user('Again', '07701234567')

    def test_dashboard_actions(self):
        admin = self.Admin.with_user(self.manager)
        data = admin.get_data()
        self.assertIn(self.staff.id, [p['id'] for p in data['people']])
        self.assertIsInstance(data['sections'], list)
        self.assertIn('no_phone', data['activity'])
        role = self.env.ref('donialink_app.role_staff')
        admin.set_roles(self.staff.id, [role.id])
        self.assertEqual(self.staff.dl_app_role_ids, role)
        admin.toggle_kind(self.kind.id, 'user', self.clerk.id, True)
        admin.toggle_kind(self.kind.id, 'role', role.id, True)
        self.assertEqual(self.kind._recipients(), self.clerk | role.user_ids)
        admin.set_kind_push(self.kind.id, False)
        self.assertFalse(self.kind.push)
        self.assertEqual(admin.test_kind(self.kind.id)['sent'], 1)
        screen = self.env.ref('donialink_app.screen_odoo')
        admin.toggle_screen(screen.id, 'user', self.staff.id, True)
        self.assertIn(self.staff, screen.user_ids)
        self.assertTrue(admin.reset_password(self.staff.id)['password'])
        sent = admin.broadcast('Meeting', 'At 5', role_ids=[role.id])
        self.assertEqual(sent['sent'], len(role.user_ids))
        admin.set_active(self.staff.id, False)
        self.assertFalse(self.staff.active)
        with self.assertRaises(UserError):
            admin.set_active(self.manager.id, False)

    def test_only_managers(self):
        admin = self.Admin.with_user(self.clerk)
        for call in (lambda: admin.get_data(), lambda: admin.create_user('X', 'x.dl'),
                     lambda: admin.set_roles(self.staff.id, []), lambda: admin.broadcast('t', 'b', user_ids=[self.staff.id]),
                     lambda: admin.toggle_kind(self.kind.id, 'user', self.clerk.id, True),
                     lambda: admin.reset_password(self.staff.id)):
            with self.assertRaises(AccessError):
                call()

    def test_no_privilege_escalation(self):
        """An App Manager who is not an administrator gives no access he doesn't have and can't touch admins."""
        system = self.env.ref('base.group_system')
        Role = self.Role.with_user(self.manager)
        admin = self.Admin.with_user(self.manager)
        with self.assertRaises(AccessError):
            Role.create({'name': 'Takeover', 'user_type': 'internal', 'group_ids': [(6, 0, system.ids)]})
        role = Role.create({'name': 'Harmless', 'user_type': 'internal'})
        with self.assertRaises(AccessError):
            role.write({'group_ids': [(4, system.id)]})
        admin_role = self.Role.create({'name': 'Admins', 'user_type': 'internal', 'group_ids': [(6, 0, system.ids)]})
        with self.assertRaises(AccessError):
            admin.set_roles(self.clerk.id, [admin_role.id])
        with self.assertRaises(AccessError):
            admin_role.with_user(self.manager).write({'user_ids': [(4, self.manager.id)]})
        with self.assertRaises(AccessError):
            admin.create_user('Evil', 'evil.dl', role_ids=[admin_role.id])
        root_admin = self.env.ref('base.user_admin')
        with self.assertRaises(AccessError):
            admin.reset_password(root_admin.id)
        with self.assertRaises(AccessError):
            admin.set_active(root_admin.id, False)
        self.assertNotIn(system, self.manager.groups_id)
        # staff (portal) are still managed
        self.assertTrue(admin.reset_password(self.staff.id)['password'])
        self.assertGreaterEqual(len(admin.reset_password(self.staff.id)['password']), 12)
        # an administrator can
        boss = self.Admin.with_user(root_admin)
        boss.set_roles(self.clerk.id, [admin_role.id])
        self.assertIn(system, self.clerk.groups_id)
        self.assertTrue(boss.reset_password(self.clerk.id)['password'])

    def test_people_of_the_selected_companies(self):
        other = self.env['res.company'].create({'name': 'DL Adm Branch'})
        self.manager.company_ids |= other
        far = new_test_user(self.env, 'dl_adm_far', groups='base.group_portal', company_id=other.id,
                            company_ids=[(6, 0, other.ids)])
        admin = self.Admin.with_user(self.manager)
        main_only = admin.with_context(allowed_company_ids=[self.env.company.id]).get_data()
        self.assertNotIn(far.id, [p['id'] for p in main_only['people']])
        self.assertIn(self.staff.id, [p['id'] for p in main_only['people']])
        branch = admin.with_context(allowed_company_ids=[other.id]).get_data()
        self.assertIn(far.id, [p['id'] for p in branch['people']])
        self.assertNotIn(self.staff.id, [p['id'] for p in branch['people']])

    def test_roles_tab(self):
        admin = self.Admin.with_user(self.manager)
        role = self.Role.browse(admin.role_create('Kitchen', 'portal')['id'])
        admin.role_save(role.id, description='Cooks and prep', is_default=True)
        self.assertTrue(role.is_default)
        self.assertFalse(self.env.ref('donialink_app.role_staff').is_default, 'one default role')
        admin.role_toggle(role.id, 'kind', self.kind.id, True)
        admin.role_toggle(role.id, 'user', self.staff.id, True)
        admin.role_toggle(role.id, 'group', self.summary.id, True)
        self.assertIn(self.staff, self.kind._recipients())
        self.assertIn(self.summary, self.staff.groups_id, 'the role gives its group')
        with self.assertRaises(AccessError):
            admin.role_toggle(role.id, 'group', self.env.ref('base.group_system').id, True)
        data = admin.get_data()
        row = next(r for r in data['roles'] if r['id'] == role.id)
        self.assertEqual((row['users'], row['kinds']), ([self.staff.id], [self.kind.id]))
        admin.role_toggle(role.id, 'user', self.staff.id, False)
        self.assertNotIn(self.summary, self.staff.groups_id, 'taken back')
        admin.role_delete(role.id)
        self.assertFalse(role.exists())
