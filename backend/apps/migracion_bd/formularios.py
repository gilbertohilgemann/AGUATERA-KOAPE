from django import forms


class PostgresFormulario(forms.Form):
    servidor = forms.CharField(label='Servidor', initial='localhost')
    puerto = forms.CharField(label='Puerto', initial='5432')
    usuario = forms.CharField(label='Usuario', initial='postgres')
    contrasena = forms.CharField(label='Contraseña', widget=forms.PasswordInput, strip=False)
    nombre = forms.RegexField(label='Nombre de la base', regex=r'^[a-zA-Z][a-zA-Z0-9_]{0,40}$',
                              initial='koape_aguateras', help_text='Se crea si no existe.')
