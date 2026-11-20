# -*- coding: utf-8 -*-
import datetime
import json
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.donialink_app.models import app_summary


@tagged('post_install', '-at_install')
class TestAppSummary(HttpCase):
    """Business summary: only for the summary group, finance cards only for finance, only the person's companies."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.has_agent = 'donialink.agent.tools' in cls.env
        cls.company = cls.env.company
        cls.other_company = cls.env['res.company'].create({'name': 'DL Summary Other Co'})
        cls.plain = new_test_user(cls.env, 'dl_sum_plain', password='dl_sum_plain1', groups='base.group_user')
        cls.viewer = new_test_user(cls.env, 'dl_sum_viewer', password='dl_sum_viewer1',
                                   groups='base.group_user,donialink_app.group_summary')
        cls.finance = new_test_user(cls.env, 'dl_sum_fin', password='dl_sum_fin1',
                                    groups='base.group_portal,donialink_app.group_finance')
        cls.Summary = cls.env['donialink.app.summary']

    def setUp(self):
        super().setUp()
        if not self.has_agent:
            self.skipTest('donialink_agent is not installed')

    def api(self, action, **params):
        response = self.url_open('/dl/app/api/%s' % action, data=json.dumps({'params': params}),
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        return response.json()['result']

    def test_groups(self):
        self.assertFalse(self.Summary._info(self.plain))
        info = self.Summary._info(self.viewer)
        self.assertEqual(info['companies'][0]['id'], self.viewer.company_id.id)
        self.assertFalse(info['finance'])
        self.assertNotIn('profit', info['parts'])
        self.assertNotIn('bills', info['parts'])
        self.assertIn('sales', info['parts'])
        finance = self.Summary._info(self.finance)
        self.assertTrue(finance['finance'], 'finance implies the summary, also for a portal user')
        self.assertIn('profit', finance['parts'])
        screens = self.env['donialink.app.screen']
        self.assertIn('summary', screens._for_user(self.viewer).mapped('key'))
        self.assertNotIn('summary', screens._for_user(self.plain).mapped('key'))

    def test_company_scoping(self):
        summary = self.Summary.with_user(self.viewer)
        card = summary.card('sales', self.company.id, 'month')
        self.assertEqual((card['company_id'], card['part'], card['period']['key']), (self.company.id, 'sales', 'month'))
        self.assertNotIn('error', card, card.get('message'))
        self.assertIn('change', card)
        with self.assertRaises(AccessError):
            summary.card('sales', self.other_company.id)
        with self.assertRaises(AccessError):
            summary.glance(self.other_company.id)
        with self.assertRaises(AccessError):
            summary.card('profit', self.company.id)   # not finance
        with self.assertRaises(AccessError):
            self.Summary.with_user(self.plain).card('sales', self.company.id)
        # with both companies, both can be read
        self.viewer.company_ids |= self.other_company
        self.assertEqual(summary.card('expenses', self.other_company.id)['company_id'], self.other_company.id)

    def test_finance_and_glance(self):
        summary = self.Summary.with_user(self.finance)
        self.assertEqual(summary.card('profit', self.company.id, 'month')['part'], 'profit')
        glance = summary.glance(self.company.id)
        self.assertEqual(glance['company_id'], self.company.id)
        self.assertIn('today', glance)
        self.assertIn('profit', glance, 'finance sees the month profit on the home page')
        self.assertNotIn('profit', self.Summary.with_user(self.viewer).glance(self.company.id))

    def test_api(self):
        self.authenticate('dl_sum_plain', 'dl_sum_plain1')
        self.assertFalse(self.api('session')['summary'])
        self.assertEqual(self.api('summary_card', part='sales', company_id=self.company.id)['error'], 'refused')
        self.authenticate('dl_sum_viewer', 'dl_sum_viewer1')
        self.assertTrue(self.api('session')['summary']['parts'])
        self.assertEqual(self.api('summary_card', part='sales', company_id=self.company.id, period='week')['part'], 'sales')
        self.assertEqual(self.api('summary_card', part='sales', company_id=self.other_company.id)['error'], 'refused')
        self.assertEqual(self.api('summary_glance', company_id=self.company.id)['company_id'], self.company.id)

    def test_without_the_agent(self):
        """Soft dependency: without donialink_agent no summary and no screen."""
        with patch.object(app_summary, 'TOOLS', 'donialink.agent.missing'):
            self.assertFalse(self.Summary._info(self.viewer))
        screen = self.env.ref('donialink_app.screen_summary')
        screen.requires_model = 'donialink.agent.missing'
        self.assertNotIn('summary', self.env['donialink.app.screen']._for_user(self.viewer).mapped('key'))

    def test_periods(self):
        day = datetime.date(2026, 11, 20)
        self.assertEqual(self.Summary._period('yesterday', day), (day - datetime.timedelta(days=1),) * 2)
        self.assertEqual(self.Summary._period('week', day), (datetime.date(2026, 11, 14), day))
        start, end = self.Summary._period('month', day)
        self.assertEqual((start, end), (datetime.date(2026, 11, 1), day))
        self.assertEqual(self.Summary._before('month', start, end), (datetime.date(2026, 10, 1), datetime.date(2026, 10, 20)))
        self.assertEqual(self.Summary._before('week', datetime.date(2026, 11, 14), day),
                         (datetime.date(2026, 11, 7), datetime.date(2026, 11, 13)))
