/** @odoo-module ignore **/
/* DoniaLink App: employee tasks. "My tasks" (today, overdue, upcoming; start, checklist, done with photo/note),
   "Team tasks" for task managers (create, assign, follow), and one task (#task-<id>). */
(function () {
    'use strict';
    const app = window.DLApp;
    const { h, t } = app;

    app.text({
        ar: {
            'My tasks': 'مهامي', 'Team tasks': 'مهام الفريق', 'Task': 'المهمة', 'Overdue': 'متأخرة', 'Today': 'اليوم',
            'Upcoming': 'القادمة', 'No date': 'بدون موعد', 'Done today': 'أُنجزت اليوم', 'Nothing to do. Well done!': 'لا شيء للقيام به. أحسنت!',
            'Start': 'ابدأ', 'Done': 'تم', 'Reopen': 'إعادة فتح', 'Cancel task': 'إلغاء المهمة', 'Checklist': 'قائمة التحقق',
            'Note': 'ملاحظة', 'Add a photo': 'أضف صورة', 'A photo is required to finish.': 'يجب إضافة صورة لإنهاء المهمة.',
            'Comments': 'التعليقات', 'Write a comment': 'اكتب تعليقاً', 'Send': 'إرسال', 'New task': 'مهمة جديدة',
            'What to do': 'ما المطلوب', 'Details': 'التفاصيل', 'Assign to': 'إسناد إلى', 'Due': 'الموعد',
            'Priority': 'الأولوية', 'Normal': 'عادية', 'High': 'مهمة', 'Urgent': 'عاجلة',
            'Checklist (one per line)': 'قائمة التحقق (سطر لكل بند)', 'Photo required to finish': 'يلزم صورة للإنهاء',
            'Repeat': 'التكرار', 'Once': 'مرة واحدة', 'Every day': 'كل يوم', 'On chosen days': 'أيام محددة',
            'Create': 'إنشاء', 'Everyone': 'الجميع', 'Open': 'المفتوحة', 'To Do': 'للتنفيذ', 'In Progress': 'قيد التنفيذ',
            'Cancelled': 'ملغاة', 'Task created.': 'تم إنشاء المهمة.', 'Done by {0}': 'أنجزها {0}', 'From {0}': 'من {0}',
            'Mon': 'الإثنين', 'Tue': 'الثلاثاء', 'Wed': 'الأربعاء', 'Thu': 'الخميس', 'Fri': 'الجمعة', 'Sat': 'السبت', 'Sun': 'الأحد',
            'Assign and follow': 'إسناد ومتابعة', 'What to do today': 'ما عليك اليوم',
        },
    });

    const STATES = { todo: 'To Do', progress: 'In Progress', done: 'Done', cancelled: 'Cancelled' };
    const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

    function when(value) {
        if (!value) {
            return '';
        }
        const d = new Date(value.replace(' ', 'T') + 'Z');
        return d.toLocaleString(app.lang === 'ar' ? 'ar-IQ' : 'en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    }

    function taskRow(task) {
        return h('a', { class: 'dl-task' + (task.overdue ? ' overdue' : '') + (task.state === 'done' ? ' done' : ''), href: '#task-' + task.id }, [
            h('span', { class: 'dl-task-mark' }, app.icon(task.state === 'done' ? 'check' : (task.overdue ? 'alert' : 'box'))),
            h('span', { class: 'dl-msg-main' }, [
                h('span', { class: 'dl-msg-title' }, (task.priority !== '0' ? '★ ' : '') + task.name),
                h('span', { class: 'dl-msg-meta' }, [
                    task.deadline ? when(task.deadline) : '',
                    task.lines ? task.lines_done + '/' + task.lines : '',
                    task.mine ? '' : task.users.map((u) => u.name).join(', '),
                ].filter(Boolean).join(' · ')),
            ]),
            h('span', { class: 'dl-pill ' + task.state }, t(STATES[task.state])),
        ]);
    }

    function groupSection(title, tasks) {
        if (!tasks.length) {
            return null;
        }
        return h('section', { class: 'dl-card flush' }, [h('h2', { class: 'dl-card-title' }, t(title)), h('div', { class: 'dl-list' }, tasks.map(taskRow))]);
    }

    // ------------------------------------------------------------------ my tasks

    app.screen('tasks', {
        async render(el) {
            el.append(app.topbar(t('My tasks'), true));
            const body = h('div', { class: 'dl-stack' });
            el.append(body);
            const data = await app.rpc('tasks_mine');
            const now = new Date();
            const endOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
            const due = (task) => (task.deadline ? new Date(task.deadline.replace(' ', 'T') + 'Z') : null);
            const open = data.tasks.filter((x) => x.state !== 'done');
            const groups = [
                ['Overdue', open.filter((x) => x.overdue)],
                ['Today', open.filter((x) => !x.overdue && due(x) && due(x) < endOfDay)],
                ['Upcoming', open.filter((x) => due(x) && due(x) >= endOfDay)],
                ['No date', open.filter((x) => !due(x))],
                ['Done today', data.tasks.filter((x) => x.state === 'done')],
            ];
            const sections = groups.map(([title, list]) => groupSection(title, list)).filter(Boolean);
            body.append(...(open.length ? sections : [h('p', { class: 'dl-empty' }, t('Nothing to do. Well done!')), ...sections]));
        },
    });

    // ------------------------------------------------------------------ team tasks

    app.screen('team_tasks', {
        async render(el) {
            el.append(app.topbar(t('Team tasks'), true));
            const body = h('div', { class: 'dl-stack' });
            el.append(body);
            let person = '';
            let state = '';
            const list = h('div', { class: 'dl-stack' });
            const data = await app.rpc('tasks_team', {});
            const people = data.people;
            const personSelect = h('select', { class: 'dl-select', onchange: () => { person = personSelect.value; load(); } },
                [h('option', { value: '' }, t('Everyone')), ...people.map((p) => h('option', { value: String(p.id) }, p.name))]);
            const stateSelect = h('select', { class: 'dl-select', onchange: () => { state = stateSelect.value; load(); } },
                [h('option', { value: '' }, t('Open')), ...['todo', 'progress', 'done', 'cancelled'].map((s) => h('option', { value: s }, t(STATES[s])))]);
            body.append(h('div', { class: 'dl-row' }, [personSelect, stateSelect]), createForm(people, load), list);
            async function load() {
                const d = await app.rpc('tasks_team', { user_id: person ? parseInt(person, 10) : null, state: state || null });
                list.replaceChildren(d.tasks.length ? h('div', { class: 'dl-card flush' }, h('div', { class: 'dl-list' }, d.tasks.map(taskRow)))
                    : h('p', { class: 'dl-empty' }, t('Nothing to do. Well done!')));
            }
            load();
        },
    });

    function createForm(people, reload) {
        const chosen = new Set();
        const name = h('input', { class: 'dl-input', required: true, placeholder: t('What to do') });
        const details = h('textarea', { class: 'dl-input', rows: 2, placeholder: t('Details') });
        const deadline = h('input', { class: 'dl-input', type: 'datetime-local' });
        const priority = h('select', { class: 'dl-select' }, [['0', 'Normal'], ['1', 'High'], ['2', 'Urgent']].map(([v, l]) => h('option', { value: v }, t(l))));
        const lines = h('textarea', { class: 'dl-input', rows: 3, placeholder: t('Checklist (one per line)') });
        const photo = h('input', { type: 'checkbox' });
        const repeat = h('select', { class: 'dl-select' }, [['none', 'Once'], ['daily', 'Every day'], ['weekly', 'On chosen days']].map(([v, l]) => h('option', { value: v }, t(l))));
        const days = new Set();
        const dayBox = h('div', { class: 'dl-chips', hidden: true }, DAYS.map((d, i) => {
            const b = h('button', { type: 'button', 'aria-selected': 'false', onclick: () => {
                if (days.has(i)) { days.delete(i); } else { days.add(i); }
                b.setAttribute('aria-selected', String(days.has(i)));
            } }, t(d));
            return b;
        }));
        repeat.onchange = () => { dayBox.hidden = repeat.value !== 'weekly'; };
        const who = h('div', { class: 'dl-chips wrap' }, people.map((p) => {
            const b = h('button', { type: 'button', 'aria-selected': 'false', onclick: () => {
                if (chosen.has(p.id)) { chosen.delete(p.id); } else { chosen.add(p.id); }
                b.setAttribute('aria-selected', String(chosen.has(p.id)));
            } }, p.name);
            return b;
        }));
        const form = h('form', { class: 'dl-card dl-form', onsubmit: async (ev) => {
            ev.preventDefault();
            try {
                await app.rpc('task_create', {
                    name: name.value, user_ids: [...chosen], description: details.value,
                    deadline: deadline.value ? new Date(deadline.value).toISOString().slice(0, 19).replace('T', ' ') : null,
                    priority: priority.value, lines: lines.value.split('\n').map((x) => x.trim()).filter(Boolean),
                    photo_required: photo.checked, repeat: repeat.value, repeat_weekdays: [...days].sort().join(',') || null,
                });
                app.toast(t('Task created.'), 'ok');
                form.reset();
                chosen.clear();
                who.querySelectorAll('button').forEach((b) => b.setAttribute('aria-selected', 'false'));
                reload();
            } catch (e) { app.toast(e.message, 'bad'); }
        } }, [
            h('h2', {}, t('New task')), name, details,
            h('label', {}, t('Assign to')), who,
            h('label', {}, t('Due')), deadline,
            h('label', {}, t('Priority')), priority, lines,
            h('label', { class: 'dl-check' }, [photo, t('Photo required to finish')]),
            h('label', {}, t('Repeat')), repeat, dayBox,
            h('button', { class: 'dl-btn', type: 'submit' }, t('Create')),
        ]);
        return h('details', { class: 'dl-card' }, [h('summary', {}, '+ ' + t('New task')), form]);
    }

    // ------------------------------------------------------------------ one task

    function readFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve({ filename: file.name, mimetype: file.type || 'image/jpeg', content_b64: String(reader.result).split(',')[1] });
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    app.screen('task', {
        always: true,   // reached from a notification; the server checks the access
        async render(el, params) {
            el.append(app.topbar(t('Task'), true));
            const body = h('div', { class: 'dl-stack' });
            el.append(body);
            let task = (await app.rpc('task', { task_id: parseInt(params[0], 10) })).task;
            const photos = [];
            async function act(action, extra) {
                try {
                    task = (await app.rpc('task_do', Object.assign({ task_id: task.id, step: action }, extra || {}))).task;
                    draw();
                } catch (e) { app.toast(e.message, 'bad'); }
            }
            function draw() {
                const open = task.state === 'todo' || task.state === 'progress';
                const note = h('textarea', { class: 'dl-input', rows: 2, placeholder: t('Note') });
                const fileInput = h('input', { type: 'file', accept: 'image/*', capture: 'environment', hidden: true, multiple: true, onchange: async () => {
                    for (const f of fileInput.files) { photos.push(await readFile(f)); }
                    photoLabel.textContent = '📷 ' + photos.length;
                } });
                const photoLabel = h('span', {}, photos.length ? '📷 ' + photos.length : '');
                body.replaceChildren(...[
                    h('section', { class: 'dl-card' }, [
                        h('div', { class: 'dl-card-head' }, [h('h2', {}, (task.priority !== '0' ? '★ ' : '') + task.name), h('span', { class: 'dl-pill ' + task.state }, t(STATES[task.state]))]),
                        task.deadline ? h('p', { class: task.overdue ? 'dl-error' : 'dl-muted' }, t('Due') + ': ' + when(task.deadline)) : null,
                        task.description ? h('p', { class: 'dl-pre' }, task.description) : null,
                        h('p', { class: 'dl-muted' }, [t('From {0}', task.creator), ' · ', task.users.map((u) => u.name).join(', ')].join('')),
                        task.done_by ? h('p', { class: 'dl-muted' }, t('Done by {0}', task.done_by) + (task.done_note ? ' · ' + task.done_note : '')) : null,
                    ]),
                    task.checklist.length ? h('section', { class: 'dl-card' }, [h('h2', {}, t('Checklist')), ...task.checklist.map((line) => h('label', { class: 'dl-check' }, [
                        h('input', { type: 'checkbox', checked: line.done, disabled: !open, onchange: async (ev) => {
                            task = (await app.rpc('task_line', { line_id: line.id, done: ev.target.checked })).task;
                        } }), line.name,
                    ]))]) : null,
                    task.photos.length ? h('section', { class: 'dl-card dl-photos' }, task.photos.map((p) => h('a', { href: p.url, target: '_blank' }, h('img', { src: p.url, alt: p.name })))) : null,
                    open ? h('section', { class: 'dl-card dl-stack' }, [
                        task.state === 'todo' ? h('button', { class: 'dl-btn ghost', onclick: () => act('start') }, t('Start')) : null,
                        note,
                        h('div', { class: 'dl-row' }, [h('button', { class: 'dl-btn ghost', type: 'button', onclick: () => fileInput.click() }, [app.icon('install'), t('Add a photo')]), photoLabel, fileInput]),
                        task.photo_required ? h('p', { class: 'dl-muted' }, t('A photo is required to finish.')) : null,
                        h('button', { class: 'dl-btn', onclick: () => act('done', { note: note.value, photos }) }, [app.icon('check'), t('Done')]),
                        task.can_cancel ? h('button', { class: 'dl-link', onclick: () => act('cancel') }, t('Cancel task')) : null,
                    ]) : h('button', { class: 'dl-btn ghost', onclick: () => act('reset') }, t('Reopen')),
                    commentsCard(),
                ].filter(Boolean));
            }
            function commentsCard() {
                const input = h('input', { class: 'dl-input', placeholder: t('Write a comment') });
                return h('section', { class: 'dl-card' }, [
                    h('h2', {}, t('Comments')),
                    ...task.comments.map((c) => h('div', { class: 'dl-comment' }, [h('b', {}, c.author), h('div', { html: c.body }), h('small', { class: 'dl-muted' }, app.date(c.date))])),
                    h('form', { class: 'dl-row', onsubmit: async (ev) => {
                        ev.preventDefault();
                        if (!input.value.trim()) { return; }
                        task = (await app.rpc('task_comment', { task_id: task.id, body: input.value })).task;
                        draw();
                    } }, [input, h('button', { class: 'dl-btn small', type: 'submit' }, t('Send'))]),
                ]);
            }
            draw();
        },
    });
}());
