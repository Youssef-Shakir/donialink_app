# -*- coding: utf-8 -*-
"""Business summary of the app: live figures read with the DoniaLink Agent's read tools (donialink_agent), in
process, for ONE company the person may open, over a period (today, yesterday, last 7 days, this month).

Soft dependency: without donialink_agent the summary is simply not offered. The tools read with sudo, so the
access is checked here: the groups "See business summary" / "See finance", and the company must be one of the
person's allowed companies (a call is always about one company; "All companies" is one call per company)."""
import datetime
import logging

import pytz

from odoo import _, api, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

TOOLS = 'donialink.agent.tools'
PERIODS = ('today', 'yesterday', 'week', 'month')
# card -> (tool, params)
PARTS = {
    'sales': ('sales_summary', {'group_by': 'product', 'top': 5}),
    'expenses': ('expenses_summary', {'group_by': 'category', 'top': 5}),
    'profit': ('profit_and_loss', {}),
    'differences': ('cash_differences', {'group_by': 'cashier'}),
    'bills': ('bills_to_pay', {'limit': 5}),
    'stock': ('order_now_list', {'limit': 5}),
}
FINANCE_PARTS = {'profit', 'bills'}
NO_PERIOD = {'bills', 'stock'}


class DonialinkAppSummary(models.AbstractModel):
    _name = 'donialink.app.summary'
    _description = 'DoniaLink App: Business Summary'

    # ------------------------------------------------------------------
    # Who sees what
    # ------------------------------------------------------------------

    @api.model
    def _available(self):
        return TOOLS in self.env

    @api.model
    def _sees_summary(self, user=None):
        user = user or self.env.user
        return self._available() and user.has_group('donialink_app.group_summary')

    @api.model
    def _sees_finance(self, user=None):
        user = user or self.env.user
        return self._sees_summary(user) and user.has_group('donialink_app.group_finance')

    @api.model
    def _parts(self, user=None):
        """The cards this person gets: those whose tool exists in this database (and finance ones if allowed)."""
        if not self._sees_summary(user):
            return []
        tools = self.env[TOOLS]._get_tools()
        finance = self._sees_finance(user)
        return [key for key, (tool, _p) in PARTS.items()
                if tool in tools and (finance or key not in FINANCE_PARTS)]

    @api.model
    def _company(self, company_id, user=None):
        """One of the person's companies, or AccessError (nobody sees a company they can't open)."""
        user = user or self.env.user
        try:
            company_id = int(company_id or 0)
        except (TypeError, ValueError):
            company_id = 0
        company = user.company_ids.filtered(lambda c: c.id == company_id)
        if not company:
            raise AccessError(_('You do not have access to this company.'))
        return company

    @api.model
    def _info(self, user=None):
        user = user or self.env.user
        if not self._sees_summary(user):
            return False
        companies = user.company_ids.sorted(lambda c: (c != user.company_id, c.name or ''))
        return {
            'companies': [{'id': c.id, 'name': c.name} for c in companies],
            'default_company': user.company_id.id,
            'finance': self._sees_finance(user),
            'parts': self._parts(user),
            'periods': list(PERIODS),
        }

    # ------------------------------------------------------------------
    # Periods (business days of the agent's timezone)
    # ------------------------------------------------------------------

    @api.model
    def _today(self):
        tz = pytz.timezone(self.env[TOOLS]._business_tz())
        return datetime.datetime.now(tz).date()

    @api.model
    def _period(self, key, today=None):
        today = today or self._today()
        if key == 'yesterday':
            day = today - datetime.timedelta(days=1)
            return day, day
        if key == 'week':
            return today - datetime.timedelta(days=6), today
        if key == 'month':
            return today.replace(day=1), today
        return today, today

    @api.model
    def _before(self, key, start, end):
        """The period just before, of the same length (this month: the same days of last month)."""
        days = (end - start).days + 1
        if key == 'month':
            last = start - datetime.timedelta(days=1)
            first = last.replace(day=1)
            return first, min(last, first + datetime.timedelta(days=days - 1))
        return start - datetime.timedelta(days=days), start - datetime.timedelta(days=1)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    @api.model
    def _tool(self, name, params):
        """One read tool, in process, rolled back like the agent API does for read tools. Returns the result, or
        {'error': code, 'message': ...}."""
        Tools = self.env[TOOLS].sudo()
        if name not in Tools._get_tools():
            return {'error': 'missing'}
        try:
            with self.env.cr.savepoint() as savepoint:
                result = Tools._run_tool(name, params)[1]
                savepoint.rollback()
            return result if isinstance(result, dict) else {}
        except Exception as e:  # noqa: BLE001 - a card never breaks the summary
            code = getattr(e, 'code', None) or 'error'
            _logger.info('DoniaLink App summary: %s failed: %s', name, e)
            return {'error': code, 'message': str(getattr(e, 'message', None) or e)}

    @api.model
    def card(self, part, company_id, period='today', user=None):
        """The figures of one card for one company."""
        user = user or self.env.user
        if part not in self._parts(user):
            raise AccessError(_('You can not see this part of the summary.'))
        company = self._company(company_id, user)
        tool, extra = PARTS[part]
        params = dict(extra, company_id=company.id)
        period = period if period in PERIODS else 'today'
        start, end = self._period(period)
        if part not in NO_PERIOD:
            params.update(date_from=start.isoformat(), date_to=end.isoformat())
        result = self._tool(tool, params)
        if part == 'sales' and not result.get('error'):
            b_start, b_end = self._before(period, start, end)
            before = self._tool('sales_summary', {'company_id': company.id, 'date_from': b_start.isoformat(),
                                                  'date_to': b_end.isoformat(), 'group_by': 'day', 'top': 1})
            now_total, before_total = result.get('sales_total'), before.get('sales_total')
            result['before_total'] = before_total
            result['change'] = (round((now_total - before_total) / abs(before_total) * 100)
                                if before_total and now_total is not None else None)
        return dict(result, part=part, company_id=company.id, company=company.name,
                    period={'key': period, 'from': start.isoformat(), 'to': end.isoformat()})

    @api.model
    def glance(self, company_id, user=None):
        """A company's card on the home page: today's sales, this month's sales and expenses, profit (finance)."""
        user = user or self.env.user
        if not self._sees_summary(user):
            raise AccessError(_('You can not see the business summary.'))
        company = self._company(company_id, user)
        today_start, today_end = self._period('today')
        month_start, month_end = self._period('month')
        values = {'company_id': company.id, 'company': company.name, 'currency': '', 'errors': []}
        calls = [('today', 'sales_summary', today_start, today_end, {'group_by': 'day', 'top': 1}),
                 ('month', 'sales_summary', month_start, month_end, {'group_by': 'day', 'top': 1}),
                 ('expenses', 'expenses_summary', month_start, month_end, {'top': 1})]
        if self._sees_finance(user):
            calls.append(('profit', 'profit_and_loss', month_start, month_end, {}))
        for key, tool, start, end, extra in calls:
            result = self._tool(tool, dict(extra, company_id=company.id, date_from=start.isoformat(),
                                           date_to=end.isoformat()))
            if result.get('error'):
                if result['error'] != 'missing':
                    values['errors'].append(result.get('message') or result['error'])
                continue
            values[key] = result
            values['currency'] = values['currency'] or result.get('currency') or ''
        return values
