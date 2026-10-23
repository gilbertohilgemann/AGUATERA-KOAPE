from django.contrib import admin
from django.shortcuts import render

from .models import ManualPlataforma


@admin.register(ManualPlataforma)
class ManualPlataformaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        contexto = {**self.admin_site.each_context(request), 'opts': self.model._meta, 'title': 'Manual de usuario'}
        return render(request, 'admin/manual/manual.html', contexto)
