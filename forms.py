from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired

class LoginForm(FlaskForm):
    username = StringField('Usuário', validators=[DataRequired(message="O nome de usuário é obrigatório.")])
    password = PasswordField('Senha', validators=[DataRequired(message="A senha é obrigatória.")])
    submit = SubmitField('Entrar')
