/** @odoo-module **/
/* DoniaLink App admin dashboard: who uses the app, creating users, who receives and sees what, activity and
   broadcast. Other modules add cards: Python _dl_app_admin_sections() (simple card) or an OWL component in
   registry.category('donialink_app.admin_sections') under the card's key. */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export const adminSections = registry.category("donialink_app.admin_sections");

export class DonialinkAppAdmin extends Component {
    static template = "donialink_app.AdminDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.state = useState({
            data: null, tab: "people", editRoles: null, created: null, password: null,
            form: { name: "", login: "", password: "", roles: [], companies: [] },
            broadcast: { title: "", body: "", roles: [], groups: [], users: [] },
            search: "",
        });
        this.tabs = [
            ["people", _t("People")], ["create", _t("New user")], ["receives", _t("Who receives what")],
            ["sees", _t("Who sees what")], ["activity", _t("Activity")], ["broadcast", _t("Broadcast")],
        ];
        onWillStart(() => this.load());
    }

    async call(method, ...args) {
        try {
            return await this.orm.call("donialink.app.admin", method, args);
        } catch (e) {
            this.notification.add(e.data?.message || e.message || String(e), { type: "danger" });
            throw e;
        }
    }

    async load() {
        this.state.data = await this.call("get_data");
        if (!this.state.form.companies.length && this.state.data.companies.length) {
            this.state.form.companies = [this.state.data.companies[0].id];
        }
    }

    // ---------------------------------------------------------------- helpers
    get people() {
        const q = this.state.search.toLowerCase();
        return this.state.data.people.filter((p) => !q || p.name.toLowerCase().includes(q) || (p.login || "").toLowerCase().includes(q));
    }
    roleName(id) {
        return this.state.data.roles.find((r) => r.id === id)?.name || "";
    }
    groupName(id) {
        return this.state.data.groups.find((g) => g.id === id)?.name || String(id);
    }
    personName(id) {
        return this.state.data.people.find((p) => p.id === id)?.name || String(id);
    }
    sectionComponent(section) {
        return adminSections.contains(section.key) ? adminSections.get(section.key) : null;
    }
    toggleIn(list, id) {
        const i = list.indexOf(id);
        if (i >= 0) {
            list.splice(i, 1);
        } else {
            list.push(id);
        }
    }
    lastSeen(value) {
        return value ? value.slice(0, 16) : _t("Never");
    }

    // ---------------------------------------------------------------- actions
    openAction(xmlId) {
        return this.action.doAction(xmlId);
    }
    openUser(id) {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "res.users", res_id: id, views: [[false, "form"]] });
    }
    async sendTest(person) {
        const r = await this.call("send_test", person.id);
        this.notification.add(_t("Test sent to %(name)s (%(n)s phone(s)).", { name: person.name, n: r.phones }), { type: "success" });
    }
    async resetPassword(person) {
        const r = await this.call("reset_password", person.id);
        this.state.password = { name: person.name, login: person.login, password: r.password };
    }
    async setActive(person, active) {
        await this.call("set_active", person.id, active);
        await this.load();
    }
    editRoles(person) {
        this.state.editRoles = { id: person.id, roles: [...person.roles] };
    }
    async saveRoles() {
        await this.call("set_roles", this.state.editRoles.id, this.state.editRoles.roles);
        this.state.editRoles = null;
        await this.load();
    }
    async createUser(ev) {
        ev.preventDefault();
        const f = this.state.form;
        const r = await this.call("create_user", f.name, f.login, f.password || false, f.roles, f.companies);
        this.state.created = Object.assign({ name: f.name }, r);
        Object.assign(f, { name: "", login: "", password: "", roles: [] });
        await this.load();
    }
    async toggleKind(kind, target, id, on) {
        await this.call("toggle_kind", kind.id, target, id, on);
        await this.load();
    }
    async setPush(kind, on) {
        await this.call("set_kind_push", kind.id, on);
        await this.load();
    }
    async testKind(kind) {
        const r = await this.call("test_kind", kind.id);
        this.notification.add(r.sent ? _t("Test sent to your app.") : _t("Not sent: you switched this kind off."), { type: r.sent ? "success" : "warning" });
    }
    async toggleScreen(screen, target, id, on) {
        await this.call("toggle_screen", screen.id, target, id, on);
        await this.load();
    }
    async addFromSelect(ev, fn, item, target) {
        const id = parseInt(ev.target.value, 10);
        ev.target.value = "";
        if (id) {
            await fn.call(this, item, target, id, true);
        }
    }
    addTo(ev, list) {
        const id = parseInt(ev.target.value, 10);
        ev.target.value = "";
        if (id && !list.includes(id)) {
            list.push(id);
        }
    }
    async sendBroadcast(ev) {
        ev.preventDefault();
        const b = this.state.broadcast;
        const r = await this.call("broadcast", b.title, b.body, b.roles, b.groups, b.users);
        this.notification.add(_t("Sent to %s people.", r.sent), { type: "success" });
        Object.assign(b, { title: "", body: "", roles: [], groups: [], users: [] });
        await this.load();
    }
}

registry.category("actions").add("donialink_app.admin_dashboard", DonialinkAppAdmin);
