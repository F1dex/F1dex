from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.utils.translation import gettext_lazy as _


class BallsdexAdminSite(admin.AdminSite):
    site_header = "F1Dex Configuration"
    site_title = "F1Dex admin panel"
    site_url = None  # type: ignore
    login_template = "admin/login.html"
    final_catch_all_view = False

    def each_context(self, request):
        context = super().each_context(request)
        return context

    class Media:
        css = {
            'all': ['admin/css/f1dex_main.css'],
        }

admin.site = F1DexAdminSite()
admin.autodiscover()
