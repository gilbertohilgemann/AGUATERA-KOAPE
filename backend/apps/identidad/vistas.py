from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.auditoria.servicios import registrar
from comun.vistas import VistaInstitucional

from . import servicios
from .models import Permiso, Rol, Usuario
from .permisos import RequierePermiso
from .serializadores import (
    CambioContrasenaSerializer, ConfirmarRecuperacionSerializer, IngresoSerializer, SolicitarRecuperacionSerializer, PermisoSerializer, RestablecerContrasenaSerializer, RolSerializer,
    UsuarioSerializer, puede_gestionar,
)
from .tokens import revocar, revocar_todos


class IngresarVista(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'ingreso'

    def post(self, request):
        serializador = IngresoSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        datos = serializador.validated_data
        if datos.get('sitio_web'):
            # Honeypot: se responde igual que unas credenciales incorrectas, sin revelar nada.
            return Response({'detalle': servicios.MENSAJE_GENERICO}, status=status.HTTP_400_BAD_REQUEST)
        try:
            usuario, token, clave = servicios.ingresar(
                request._request, codigo_institucion=datos['codigo_institucion'], usuario=datos['usuario'],
                contrasena=datos['contrasena'],
            )
        except servicios.ErrorIngreso as error:
            return Response({'detalle': error.mensaje}, status=error.estado_http)
        cuerpo = servicios.datos_sesion(usuario, token)
        cuerpo['token'] = clave
        return Response(cuerpo, status=status.HTTP_200_OK)


class SolicitarRecuperacionVista(APIView):
    """«Olvidé mi contraseña»: envía un código al correo del usuario. Siempre responde lo mismo."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'recuperar'

    def post(self, request):
        serializador = SolicitarRecuperacionSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        servicios.solicitar_recuperacion(request, **serializador.validated_data)
        return Response({'detalle': servicios.MENSAJE_RECUPERAR})


class ConfirmarRecuperacionVista(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'ingreso'

    def post(self, request):
        serializador = ConfirmarRecuperacionSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        d = serializador.validated_data
        servicios.confirmar_recuperacion(request, codigo_institucion=d['codigo_institucion'], usuario=d['usuario'],
                                         codigo=d['codigo'], nueva=d['contrasena_nueva'])
        return Response({'detalle': 'Contraseña guardada. Ya puede ingresar con ella.'})


class SalirVista(APIView):
    def post(self, request):
        revocar(request.auth)
        registrar('salida', request=request, entidad='sesion')
        return Response(status=status.HTTP_204_NO_CONTENT)


class YoVista(APIView):
    def get(self, request):
        return Response(servicios.datos_sesion(request.user, request.auth))


class CambiarContrasenaVista(APIView):
    # Con un token robado no se puede probar la contraseña actual sin límite.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'contrasena'
    def post(self, request):
        serializador = CambioContrasenaSerializer(data=request.data, context={'request': request})
        serializador.is_valid(raise_exception=True)
        servicios.cambiar_contrasena(request, request.user, serializador.validated_data['contrasena_nueva'])
        return Response({'detalle': 'Contraseña actualizada.'})


class PermisoVista(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'roles.administrar'
    permisos_lectura = ('usuarios.administrar',)
    serializer_class = PermisoSerializer
    pagination_class = None

    def get_queryset(self):
        return Permiso.objects.filter(vigente=True)


class RolVista(VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
               mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Los roles no se borran (quedan referenciados en la auditoría): se desactivan."""

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'roles.administrar'
    permisos_lectura = ('usuarios.administrar',)
    serializer_class = RolSerializer
    pagination_class = None
    modelo = Rol

    def get_queryset(self):
        return self.consulta_base().prefetch_related('permisos')

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'institucion': self.institucion}

    def perform_create(self, serializador):
        with transaction.atomic():
            rol = serializador.save(institucion=self.institucion)
            registrar('rol_creado', request=self.request, entidad='rol', entidad_id=rol.Code,
                      despues=servicios.foto_rol(rol))

    def perform_update(self, serializador):
        antes = servicios.foto_rol(serializador.instance)
        with transaction.atomic():
            rol = serializador.save()
            registrar('rol_modificado', request=self.request, entidad='rol', entidad_id=rol.Code,
                      antes=antes, despues=servicios.foto_rol(rol))


class UsuarioVista(VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                   mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Los usuarios no se borran (trazabilidad): se desactivan."""

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'usuarios.administrar'
    serializer_class = UsuarioSerializer
    modelo = Usuario

    def get_queryset(self):
        consulta = self.consulta_base().prefetch_related('roles').order_by('nombre_usuario')
        texto = self.request.query_params.get('buscar')
        if texto:
            from django.db.models import Q
            consulta = consulta.filter(
                Q(nombre_usuario__icontains=texto) | Q(nombre__icontains=texto)
                | Q(apellido__icontains=texto) | Q(correo__icontains=texto)
            )
        return consulta

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'institucion': self.institucion}

    def perform_create(self, serializador):
        with transaction.atomic():
            usuario = serializador.save()
            registrar('usuario_creado', request=self.request, entidad='usuario', entidad_id=usuario.nombre_usuario,
                      despues=servicios.foto_usuario(usuario))

    def perform_update(self, serializador):
        antes = servicios.foto_usuario(serializador.instance)
        correo_anterior = serializador.instance.correo
        with transaction.atomic():
            usuario = serializador.save()
            if not usuario.is_active:
                revocar_todos(usuario)
            if usuario.correo != correo_anterior:      # un código enviado al correo anterior deja de servir
                usuario.save(update_fields=servicios.anular_recuperacion(usuario))
            registrar('usuario_modificado', request=self.request, entidad='usuario', entidad_id=usuario.nombre_usuario,
                      antes=antes, despues=servicios.foto_usuario(usuario))

    @action(detail=True, methods=['post'], url_path='restablecer-contrasena')
    def restablecer_contrasena(self, request, pk=None):
        usuario = self.get_object()
        if not puede_gestionar(request.user, usuario):
            return Response({'detalle': 'No puede restablecer la contraseña de un usuario con permisos que usted no tiene.'},
                            status=status.HTTP_403_FORBIDDEN)
        serializador = RestablecerContrasenaSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        servicios.restablecer_contrasena(request, usuario, serializador.validated_data['contrasena_nueva'])
        return Response({'detalle': 'Contraseña restablecida. El usuario deberá cambiarla al ingresar.'})
