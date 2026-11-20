/** @odoo-module ignore **/
/* DoniaLink App: business summary (live figures from Odoo through the DoniaLink Agent's read tools) and the
   company glance on the home page. The server checks every call: groups and the person's companies. */
(function () {
    'use strict';
    const app = window.DLApp;
    const { h, t } = app;

    app.text({
        ar: {
            'Business summary': 'ملخص العمل', 'Your figures': 'أرقامك', 'Your companies': 'شركاتك',
            'All companies': 'كل الشركات', 'live from Odoo': 'مباشر من أودو',
            'Today': 'اليوم', 'Yesterday': 'أمس', 'Last 7 days': 'آخر 7 أيام', 'This month': 'هذا الشهر',
            'Sales': 'المبيعات', 'Expenses': 'المصاريف', 'Profit and loss': 'الأرباح والخسائر',
            'Cash differences': 'فروقات النقد', 'Bills to pay': 'فواتير للدفع', 'To order': 'مواد للطلب',
            'Owner cash boxes': 'صناديق المالك', 'Orders': 'الطلبات', 'Average ticket': 'متوسط الفاتورة',
            'Payments': 'طرق الدفع', 'Best sellers': 'الأكثر مبيعاً', 'Cancelled': 'الملغاة', 'Refunds': 'المرتجعات',
            '{0}% vs the period before': '{0}% عن الفترة السابقة', 'Total': 'المجموع', 'To pay later': 'للدفع لاحقاً',
            'Revenue': 'الإيرادات', 'Gross profit': 'الربح الإجمالي', 'Net profit': 'صافي الربح', 'Margin': 'الهامش',
            'Shortage': 'النقص', 'Overage': 'الزيادة', 'Net': 'الصافي', 'Due': 'المستحق', 'Overdue': 'متأخرة',
            '{0} items to order': '{0} مادة يجب طلبها', 'No sales in this period.': 'لا توجد مبيعات في هذه الفترة.',
            'No expenses in this period.': 'لا توجد مصاريف في هذه الفترة.',
            'No differences in this period.': 'لا فروقات في هذه الفترة.', 'No bills due.': 'لا فواتير مستحقة.',
            'Nothing to order now.': 'لا شيء يجب طلبه الآن.',
            'Not available in this Odoo.': 'غير متاح في أودو.',
            "Today's sales": 'مبيعات اليوم', "Month's sales": 'مبيعات الشهر', "Month's expenses": 'مصاريف الشهر',
            "Month's profit": 'ربح الشهر', 'Open the cash boxes': 'فتح الصناديق', 'See all': 'عرض الكل',
            '{0} sessions with a difference': '{0} جلسة فيها فرق', 'Company': 'الشركة',
            'Sales, expenses and more, live': 'المبيعات والمصاريف وأكثر، مباشرة',
        },
    });

    const PERIODS = [['today', 'Today'], ['yesterday', 'Yesterday'], ['week', 'Last 7 days'], ['month', 'This month']];
    const TITLES = {
        sales: 'Sales', expenses: 'Expenses', profit: 'Profit and loss', differences: 'Cash differences',
        bills: 'Bills to pay', stock: 'To order',
    };

    function store(key, value) {
        try {
            if (value === undefined) {
                return localStorage.getItem(key);
            }
            localStorage.setItem(key, value);
        } catch (e) { /* private mode */ }
        return null;
    }

    function info() {
        return app.session.summary || null;
    }

    /** The companies the screen shows: the chosen one, or all of them ("all", only with more than one). */
    function chosenCompanies() {
        const s = info();
        const saved = store('dl-company');
        if (saved === 'all' && s.companies.length > 1) {
            return s.companies;
        }
        const found = s.companies.find((c) => String(c.id) === saved);
        return [found || s.companies.find((c) => c.id === s.default_company) || s.companies[0]];
    }

    function money(value, currency) {
        if (typeof value !== 'number' || Number.isNaN(value)) {
            return '–';
        }
        const whole = Math.abs(value) >= 100 || Number.isInteger(value);
        const text = value.toLocaleString('en-US', { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: whole ? 0 : 2 });
        return currency ? text + ' ' + currency : text;
    }

    const num = (value, currency) => h('bdi', { class: 'dl-num' + (value < 0 ? ' neg' : '') }, money(value, currency));

    function bars(rows, currency, labelKey, amountKey) {
        return h('div', { class: 'dl-bars' }, rows.map((r) => h('div', { class: 'dl-bar', style: '--w:' + Math.max(0, Math.min(100, r.share_pct || 0)) + '%' }, [
            h('i'), h('span', {}, String(r[labelKey] || '')), num(r[amountKey], currency),
        ])));
    }

    function table(rows) {
        return h('table', { class: 'dl-figures' }, rows.filter(Boolean).map(([label, value]) => h('tr', {}, [h('th', {}, label), h('td', {}, value)])));
    }

    function kpi(value, currency, extra) {
        return h('div', { class: 'dl-kpi' }, [num(value, currency), extra || null]);
    }

    // ------------------------------------------------------------------ cards

    const RENDER = {
        sales(d) {
            if (!d.orders) {
                return h('p', { class: 'dl-empty' }, t('No sales in this period.'));
            }
            const c = d.currency;
            const pill = typeof d.change === 'number'
                ? h('span', { class: 'dl-trend ' + (d.change >= 0 ? 'up' : 'down') }, (d.change >= 0 ? '▲ ' : '▼ ') + t('{0}% vs the period before', Math.abs(d.change)))
                : null;
            return [
                kpi(d.sales_total, c, pill),
                table([
                    [t('Orders'), h('bdi', {}, String(d.orders))],
                    [t('Average ticket'), num(d.average_ticket, c)],
                    d.cancelled && d.cancelled.orders ? [t('Cancelled'), h('bdi', {}, d.cancelled.orders + ' · ' + money(d.cancelled.amount, c))] : null,
                    d.refunds && d.refunds.orders ? [t('Refunds'), h('bdi', {}, d.refunds.orders + ' · ' + money(d.refunds.amount, c))] : null,
                ]),
                (d.payment_methods || []).length ? h('h4', {}, t('Payments')) : null,
                (d.payment_methods || []).length ? bars(d.payment_methods, c, 'method', 'amount') : null,
                (d.groups || []).length ? h('h4', {}, t('Best sellers')) : null,
                (d.groups || []).length ? bars(d.groups, c, 'key', 'amount') : null,
            ];
        },
        expenses(d) {
            if (!d.expenses) {
                return h('p', { class: 'dl-empty' }, t('No expenses in this period.'));
            }
            const c = d.currency;
            return [
                kpi(d.total, c),
                table([
                    [t('Expenses'), h('bdi', {}, String(d.expenses))],
                    d.to_pay_later ? [t('To pay later'), num(d.to_pay_later, c)] : null,
                ]),
                bars(d.groups || [], c, 'key', 'amount'),
            ];
        },
        profit(d) {
            const c = d.currency;
            const margin = d.revenue ? Math.round((d.net_profit / d.revenue) * 100) : null;
            return [
                kpi(d.net_profit, c, margin !== null ? h('span', { class: 'dl-muted' }, t('Net profit') + ' · ' + t('Margin') + ' ' + margin + '%') : null),
                table([
                    [t('Revenue'), num(d.revenue, c)],
                    [t('Gross profit'), num(d.gross_profit, c)],
                    ...(d.sections || []).filter((s) => s.amount && s.key !== 'revenue' && s.title).map((s) => [s.title, num(s.amount, c)]),
                ]),
            ];
        },
        differences(d) {
            if (!d.sessions_with_difference) {
                return h('p', { class: 'dl-empty' }, t('No differences in this period.'));
            }
            const c = d.currency;
            return [
                kpi(d.net_difference, c, h('span', { class: 'dl-muted' }, t('{0} sessions with a difference', d.sessions_with_difference))),
                table([[t('Shortage'), num(-Math.abs(d.total_shortage || 0), c)], [t('Overage'), num(d.total_overage, c)]]),
                h('div', { class: 'dl-bars' }, (d.groups || []).slice(0, 5).map((g) => h('div', { class: 'dl-bar' }, [
                    h('i'), h('span', {}, String(g.key || '')), num(g.net !== undefined ? g.net : g.amount, c)]))),
            ];
        },
        bills(d) {
            if (!d.bills) {
                return h('p', { class: 'dl-empty' }, t('No bills due.'));
            }
            const c = d.currency;
            return [
                kpi(d.total_due, c, h('span', { class: 'dl-muted' }, t('Due') + ' · ' + d.bills)),
                d.overdue_count ? h('span', { class: 'dl-badge warn' }, t('Overdue') + ': ' + d.overdue_count + ' · ' + money(d.overdue_due, c)) : null,
                h('div', { class: 'dl-bars' }, (d.by_supplier || []).slice(0, 5).map((s) => h('div', { class: 'dl-bar' }, [
                    h('i'), h('span', {}, String(s.supplier || '')), num(s.due, c)]))),
            ];
        },
        stock(d) {
            const items = d.items || [];
            if (!d.count) {
                return h('p', { class: 'dl-empty' }, t('Nothing to order now.'));
            }
            return [
                h('p', { class: 'dl-kpi-text' }, t('{0} items to order', d.count)),
                h('div', { class: 'dl-list' }, items.map((i) => h('div', { class: 'dl-line' }, [
                    h('span', {}, [i.name || i.product || '', i.vendor ? h('small', { class: 'dl-muted' }, ' · ' + i.vendor) : null]),
                    h('bdi', {}, (i.order_qty_purchase_uom !== undefined && i.order_qty_purchase_uom !== null
                        ? i.order_qty_purchase_uom + ' ' + (i.purchase_uom || '') : (i.order_qty || '') + ' ' + (i.uom || ''))),
                ]))),
            ];
        },
    };

    function errorText(e) {
        return e && (e.error === 'missing' || e.code === 'missing') ? t('Not available in this Odoo.') : (e.message || t('Server error. Try again.'));
    }

    async function fillBlock(block, part, company, period) {
        try {
            const d = await app.rpc('summary_card', { part, company_id: company.id, period });
            block.replaceChildren(...[].concat(d.error ? h('p', { class: 'dl-error' }, errorText(d)) : RENDER[part](d)).filter(Boolean));
        } catch (e) {
            block.replaceChildren(h('p', { class: 'dl-error' }, errorText(e)));
        }
    }

    function companyPicker(onChange) {
        const s = info();
        if (s.companies.length < 2) {
            return null;
        }
        const chosen = chosenCompanies();
        const select = h('select', { class: 'dl-select', 'aria-label': t('Company'), onchange: () => {
            store('dl-company', select.value);
            onChange();
        } }, [
            h('option', { value: 'all', selected: chosen.length > 1 }, t('All companies')),
            ...s.companies.map((c) => h('option', { value: String(c.id), selected: chosen.length === 1 && chosen[0].id === c.id }, c.name)),
        ]);
        return select;
    }

    // ------------------------------------------------------------------ summary screen

    app.screen('summary', {
        async render(el) {
            const s = info();
            if (!s) {
                return app.go('');
            }
            let period = store('dl-period') || 'today';
            el.append(app.topbar(t('Business summary'), true));
            const picker = companyPicker(() => draw());
            const chips = h('div', { class: 'dl-chips', role: 'tablist' }, PERIODS.map(([key, label]) => h('button', {
                role: 'tab', 'aria-selected': String(key === period), onclick: (ev) => {
                    period = key;
                    store('dl-period', key);
                    chips.querySelectorAll('button').forEach((b) => b.setAttribute('aria-selected', String(b === ev.currentTarget)));
                    draw();
                },
            }, t(label))));
            const head = h('div', { class: 'dl-summary-head' }, [
                h('span', { class: 'dl-live' }, [h('i'), t('live from Odoo')]), picker,
            ]);
            const cards = h('div', { class: 'dl-stack' });
            el.append(h('div', { class: 'dl-stack' }, [head, chips, cards]));
            function draw() {
                const companies = chosenCompanies();
                cards.replaceChildren();
                for (const part of s.parts) {
                    const card = h('section', { class: 'dl-card dl-fig' }, h('h3', {}, t(TITLES[part])));
                    cards.append(card);
                    for (const company of companies) {
                        if (companies.length > 1) {
                            card.append(h('h4', { class: 'dl-fig-company' }, company.name));
                        }
                        const block = h('div', { class: 'dl-fig-body' }, h('div', { class: 'dl-skeleton' }));
                        card.append(block);
                        fillBlock(block, part, company, period);
                    }
                }
                if ((app.session.screens || []).some((x) => x.key === 'cashbox')) {
                    cards.append(h('a', { class: 'dl-card dl-fig-link', href: '#cashbox' }, [
                        app.icon('cash'), h('span', {}, t('Owner cash boxes')), h('span', { class: 'dl-muted' }, t('Open the cash boxes')),
                    ]));
                }
            }
            draw();
        },
    });

    // ------------------------------------------------------------------ home: company glance

    function glanceCard(company, single) {
        const s = info();
        const card = h('section', { class: 'dl-card dl-glance' });
        const top = h('button', { class: 'dl-glance-head', onclick: () => {
            store('dl-company', String(company.id));
            app.go('summary');
        } }, [h('b', {}, company.name), h('span', { class: 'dl-muted' }, '…')]);
        const grid = h('div', { class: 'dl-glance-grid' }, h('div', { class: 'dl-skeleton' }));
        card.append(single ? h('div', { class: 'dl-card-head' }, [h('h2', {}, t('Your figures')), h('a', { href: '#summary' }, t('See all'))]) : null, top, grid);
        app.rpc('summary_glance', { company_id: company.id }).then((g) => {
            const c = g.currency;
            const today = g.today || {};
            top.lastChild.textContent = t("Today's sales") + ': ' + money(today.sales_total, c) + (today.orders ? ' · ' + today.orders + ' ' + t('Orders') : '');
            const tiles = [[t("Month's sales"), (g.month || {}).sales_total], [t("Month's expenses"), (g.expenses || {}).total]];
            if (s.finance && g.profit) {
                tiles.push([t("Month's profit"), g.profit.net_profit]);
            }
            grid.replaceChildren(...tiles.map(([label, value]) => h('div', { class: 'dl-glance-tile' }, [h('span', {}, label), num(value, c)])));
            if (g.errors && g.errors.length) {
                grid.append(h('p', { class: 'dl-error' }, g.errors[0]));
            }
        }).catch((e) => grid.replaceChildren(h('p', { class: 'dl-error' }, errorText(e))));
        return card;
    }

    app.summaryHome = function (container) {
        const s = info();
        if (!s || !s.parts.length) {
            return;
        }
        const wrap = h('div', { class: 'dl-stack' });
        function draw() {
            const companies = chosenCompanies();
            const head = h('div', { class: 'dl-summary-head' }, [
                h('h2', {}, companies.length > 1 ? t('Your companies') : t('Business summary')),
                companyPicker(draw),
            ]);
            wrap.replaceChildren(head, ...companies.map((c) => glanceCard(c, companies.length === 1)));
        }
        draw();
        container.append(wrap);
    };
}());
