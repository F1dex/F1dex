from django.contrib import admin


class BallsdexAdminSite(admin.AdminSite):
    site_header = "F1Dex Configuration"
    site_title = "F1Dex admin panel"
    site_url = None  # type: ignore
    final_catch_all_view = False
