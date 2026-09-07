/** @odoo-module **/

import { FormCompiler } from "@web/views/form/form_compiler";
import { patch } from "@web/core/utils/patch";
import { createElement, append } from "@web/core/utils/xml";

patch(FormCompiler.prototype, {
  compile(key, params = {}) {
    const compiled = super.compile(...arguments);
    if (!params.isSubView) {
      const chatterContainer = compiled.querySelector(
        ".o-mail-Form-chatter:not(.o-isInFormSheetBg)"
      );
      if (chatterContainer) {
        const chatterParent = chatterContainer.parentNode;
        const toggleWrapper = createElement("div");
        toggleWrapper.classList.add(
          "o_chatter_toggle_wrapper",
          "position-relative"
        );
        const chatterToggle = this.createChatterToggleButton();
        append(toggleWrapper, chatterToggle);
        if (chatterParent) {
          chatterParent.insertBefore(toggleWrapper, chatterContainer);
        }
      }
    }
    return compiled;
  },

  createChatterToggleButton() {
    const toggleButton = createElement("t");
    toggleButton.setAttribute("t-call", "ms_hide_chatter.ChatterToggleButton");
    return toggleButton;
  },
});
