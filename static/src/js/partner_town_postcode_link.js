/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

/**
 * Renders a many2one field (from_location/to_location) as plain
 * "Town, Postcode" text — pulled from a sibling computed Char field —
 * while keeping the click-through to the linked partner record that the
 * default many2one widget gives for free.
 *
 * Used only on the Transport Legs list (sale_transport_leg_list_view):
 * the client wants the address text shortened but not the ability to
 * open the contact behind it.
 */
export class PartnerTownPostcodeLink extends Component {
    static template = "sale_goods_order.PartnerTownPostcodeLink";
    static props = {
        ...standardFieldProps,
        textFieldName: { type: String, optional: true },
    };

    setup() {
        this.actionService = useService("action");
    }

    get displayText() {
        const fieldName = this.props.textFieldName;
        return (fieldName && this.props.record.data[fieldName]) || "";
    }

    get partnerId() {
        const value = this.props.record.data[this.props.name];
        return value ? value[0] : false;
    }

    async openPartner(ev) {
        ev.preventDefault();
        if (!this.partnerId) {
            return;
        }
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: this.partnerId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("fields").add("partner_town_postcode_link", {
    component: PartnerTownPostcodeLink,
    extractProps: ({ options }) => ({
        textFieldName: options.text_field,
    }),
});
