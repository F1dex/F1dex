import os
import random

from django.conf import settings
from django.contrib import admin


class BallsdexAdminSite(admin.AdminSite):
    def login(self, request, extra_context=None):
        img_dir = os.path.abspath(os.path.join(settings.BASE_DIR, "..", "static", "admin_backgrounds"))
        try:
            images = [f for f in os.listdir(img_dir) if f.endswith((".jpg", ".png"))]
        except FileNotFoundError:
            images = []
    
        background_url = f"/static/admin_backgrounds/{random.choice(images)}" if images else None
    
        if extra_context is None:
            extra_context = {}
        extra_context["background_url"] = background_url
        return super().login(request, extra_context)
