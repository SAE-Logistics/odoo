# -*- coding: utf-8 -*-

from . import models
from . import booking


def post_init_hook(env):
    """Enable lot/package tracking so parcels can be created on pickings."""
    config = env["res.config.settings"].create({
        "group_stock_tracking_lot": True,
    })
    config.execute()
