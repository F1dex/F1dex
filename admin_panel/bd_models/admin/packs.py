from django.contrib import admin

from ..models import Packs


@admin.register(Packs)
class PacksAdmin(admin.ModelAdmin):
    fields = (("name", "price"), "description", "rewards", ("purchasable", "created_at"))
    readonly_fields = ("created_at",)
    list_display = ("name", "price", "purchasable", "created_at")
    list_filter = ("purchasable",)
    search_fields = ("name",)
