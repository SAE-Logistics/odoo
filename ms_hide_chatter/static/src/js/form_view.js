/** @odoo-module **/

import { FormRenderer } from "@web/views/form/form_renderer";
import { patch } from "@web/core/utils/patch";
import { useState, useRef } from "@odoo/owl";

const formRendererPatch = {
  setup() {
    super.setup();
    this.chatterState = useState({
      isChatterVisible: true,
    });
    this.root = useRef("root");
    this.toggleChatter = this.toggleChatter.bind(this);
  },

  toggleChatter() {
    this.chatterState.isChatterVisible = !this.chatterState.isChatterVisible;
    const root = document.querySelector(".o_content");
    if (!root) return;

    const chatterContainer = root.querySelector(
      ".o-mail-Form-chatter:not(.o-isInFormSheetBg)"
    );
    if (chatterContainer) {
      chatterContainer.style.display = this.chatterState.isChatterVisible
        ? "block"
        : "none";

      const formView = root.querySelector(".o_form_view");
      if (formView) {
        formView.style.display = "flex";
        formView.style.flexDirection = "row";
        formView.style.flexWrap = this.chatterState.isChatterVisible
          ? "nowrap"
          : "wrap";

        const formSheetBg = formView.querySelector(".o_form_sheet_bg");
        if (formSheetBg) {
          formSheetBg.style.flexGrow = "1";
          formSheetBg.style.width = this.chatterState.isChatterVisible
            ? "70%"
            : "100%";
        }
      }
    }
  },
};

patch(FormRenderer.prototype, formRendererPatch);
