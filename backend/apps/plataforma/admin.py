"""
Instituciones en el panel de la plataforma.

- Alta con su administrador inicial (servicio `crear_institucion`, todo o nada).
- El código institucional no se cambia después del alta (forma parte del ingreso de cada usuario).
- Las instituciones no se borran: se suspenden, se archivan o se reactivan con un motivo.
"""
from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from apps.auditoria.servicios import registrar
from comun.errores import ErrorNegocio

from . import servicios
from .formularios import AltaInstitucionForm, CambioEstadoForm
from .models import Institucion


@admin.register(Institucion)
class InstitucionAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'ruc', 'estado', 'modalidad_facturacion', 'cantidad_usuarios', 'creado_en',
                    'boton_estado')
    list_filter = ('estado', 'modalidad_facturacion')
    search_fields = ('codigo', 'nombre', 'ruc', 'correo')
    readonly_fields = ('codigo', 'estado', 'motivo_estado', 'creado_en', 'actualizado_en')
    fieldsets = (
        (None, {'fields': ('codigo', 'nombre', 'ruc', 'logo')}),
        ('Contacto', {'fields': ('direccion', 'telefono', 'correo', 'contacto')}),
        ('Estado', {'fields': ('estado', 'motivo_estado')}),
        ('Configuración', {'fields': ('zona_horaria', 'configuracion_regional', 'modalidad_facturacion',
                                      'configuracion_facturacion', 'configuracion_tarifas', 'portal_abonados')}),
        ('Fechas', {'fields': ('creado_en', 'actualizado_en')}),
    )

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs['form'] = AltaInstitucionForm
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                ('Institución', {'fields': ('codigo', 'nombre', 'ruc', 'logo', 'direccion', 'telefono', 'correo',
                                            'contacto', 'zona_horaria', 'configuracion_regional')}),
                ('Administrador inicial', {'fields': ('admin_usuario', 'admin_nombre', 'admin_correo',
                                                      'admin_contrasena')}),
            )
        return super().get_fieldsets(request, obj)

    def get_readonly_fields(self, request, obj=None):
        return () if obj is None else self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='usuarios')
    def cantidad_usuarios(self, obj):
        return obj.usuarios.filter(is_active=True).count()

    @admin.display(description='')
    def boton_estado(self, obj):
        return format_html('<a class="button" href="{}">Cambiar estado</a>',
                           reverse('admin:plataforma_institucion_estado', args=[obj.pk]))

    def save_model(self, request, obj, form, change):
        if change:
            antes = servicios.foto_institucion(Institucion.objects.get(pk=obj.pk))
            super().save_model(request, obj, form, change)
            registrar('institucion_modificada', request=request, usuario=request.user, institucion=obj,
                      entidad='institucion', entidad_id=obj.codigo, antes=antes, despues=servicios.foto_institucion(obj))
            return
        datos = {campo: form.cleaned_data[campo] for campo in AltaInstitucionForm.Meta.fields if campo in form.cleaned_data}
        nueva = servicios.crear_institucion(
            datos=datos, admin_usuario=form.cleaned_data['admin_usuario'],
            admin_contrasena=form.cleaned_data['admin_contrasena'], admin_nombre=form.cleaned_data.get('admin_nombre', ''),
            admin_correo=form.cleaned_data.get('admin_correo', ''), actor=request.user, request=request,
        )
        obj.pk = nueva.pk
        obj.refresh_from_db()

    def save_related(self, request, form, formsets, change):
        if change:
            super().save_related(request, form, formsets, change)

    def get_urls(self):
        return [
            path('<int:pk>/estado/', self.admin_site.admin_view(self.vista_estado), name='plataforma_institucion_estado'),
        ] + super().get_urls()

    def vista_estado(self, request, pk):
        institucion = get_object_or_404(Institucion, pk=pk)
        if not request.user.is_superuser:
            return redirect('admin:plataforma_institucion_changelist')
        formulario = CambioEstadoForm(request.POST or None, initial={'estado': institucion.estado})
        if request.method == 'POST' and formulario.is_valid():
            try:
                servicios.cambiar_estado(institucion, formulario.cleaned_data['estado'],
                                         motivo=formulario.cleaned_data['motivo'], actor=request.user, request=request)
            except ErrorNegocio as error:
                messages.error(request, str(error))
            else:
                messages.success(request, 'Estado actualizado.')
                return redirect('admin:plataforma_institucion_changelist')
        contexto = {**self.admin_site.each_context(request), 'opts': self.model._meta, 'institucion': institucion,
                    'formulario': formulario, 'title': f'Cambiar estado de {institucion}'}
        return render(request, 'admin/plataforma/institucion/estado.html', contexto)
