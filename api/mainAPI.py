from flask import Flask, jsonify, request
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.security import Security, SQLAlchemyUserDatastore, UserMixin, RoleMixin, login_required
from flask_security import auth_token_required, current_user, roles_required
from flask_security.utils import encrypt_password, verify_and_update_password

from jinja2 import Environment, FileSystemLoader

from auth import forms
from core import config, interface, logging

import executionAPI
import ssl, json, os

#Create Flask App
app = Flask(__name__)

app.config.update(
        #CHANGE SECRET KEY AND SECURITY PASSWORD SALT!!!
        SECRET_KEY = "SHORTSTOPKEYTEST",
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.abspath(config.globalConfig["dbPath"]),
        SECURITY_PASSWORD_HASH = 'pbkdf2_sha512',
        SECURITY_TRACKABLE = False,
        SECURITY_PASSWORD_SALT = 'something_super_secret_change_in_production',
        SECURITY_POST_LOGIN_VIEW = '/',
        WTF_CSRF_ENABLED = False
    )

#Template Loader
env = Environment(loader=FileSystemLoader('../apps'))

#Database Connection Object
db = SQLAlchemy(app)

#Base Class for Tables
class Base(db.Model):
    __abstract__ = True
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    modified_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

#Stores Device Information
class Device(Base):
    __tablename__ = 'devices'

    name = db.Column(db.String(80))
    app = db.Column(db.String(80))
    username = db.Column(db.String(80))
    password = db.Column(db.String(80))
    ip = db.Column(db.String(15))
    port = db.Column(db.Integer())

    def __init__(self, name="", app="", username="", password="", ip="0.0.0.0", port=0):
        self.name = name
        self.app = app
        self.username = username
        self.password = password
        self.ip = ip
        self.port = port

    def editDevice(self, form):
        if form.name.data != "" and form.name.data != None:
            self.name = form.name.data

        if form.app.data != "" and form.app.data != None:
            self.app = form.app.data

        if form.username.data != "" and form.username.data != None:
            self.username = form.username.data

        if form.password.data != "" and form.password.data != None:
            self.password = form.password.data

        if form.ip.data != "" and form.ip.data != None:
            self.ip = form.ip.data

        if form.port.data != "" and form.port.data != None:
            self.port = form.port.data

    def __repr__(self):
        return json.dumps({"name" : self.name, "app" : self.app, "username" : self.username, "password" : self.password, "ip" : self.ip, "port" : str(self.port)})

#Define Models
roles_users = db.Table('roles_users',
        db.Column('user_id', db.Integer(), db.ForeignKey('auth_user.id')),
        db.Column('role_id', db.Integer(), db.ForeignKey('auth_role.id')))

class Role(Base, RoleMixin):
    __tablename__ = 'auth_role'
    name = db.Column(db.String(80), unique=True)
    description = db.Column(db.String(255))

    def __init__(self, name, description):
        self.name = name
        self.description = description

    def setDescription(self, description):
        self.description = description

    def toString(self):
        return {"name" : self.name, "description" : self.description}

    def __repr__(self):
        return '<Role %r>' % self.name

class User(Base, UserMixin):
    __tablename__ = 'auth_user'
    email = db.Column(db.String(255), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean())
    confirmed_at = db.Column(db.DateTime())
    roles = db.relationship('Role', secondary=roles_users, backref=db.backref('users', lazy='dynamic'))


    last_login_at = db.Column(db.DateTime())
    current_login_at = db.Column(db.DateTime())
    last_login_ip = db.Column(db.String(45))
    current_login_ip = db.Column(db.String(45))
    login_count = db.Column(db.Integer)

    def display(self):
        result = {}
        result["username"] = self.email
        roles = []
        for role in self.roles:
            roles.append(role.toString())
        result["roles"] = roles
        result["active"] = self.active

        return result

    def setRoles(self, roles):
        for role in roles:
            if role.data != "" and not self.has_role(role.data):
                q = user_datastore.find_role(role.data)
                if q != None:
                    user_datastore.add_role_to_user(self, q)
                    print "ADDED ROLE"
                else:
                    print "ROLE DOES NOT EXIST"
            else:
                print "HAS ROLE"

    def __repr__(self):
        return '<User %r>' % self.email

#Setup Flask Security
user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(app, user_datastore)

#Creates Test Data
@app.before_first_request
def create_user():
    #db.drop_all()
    db.create_all()
    if not User.query.first():
        #Add Credentials to Splunk app
        #db.session.add(Device(name="deviceOne", app="splunk", username="admin", password="hello", ip="192.168.0.1", port="5000"))

        adminRole = user_datastore.create_role(name="admin", description="administrator")
        #userRole = user_datastore.create_role(name="user", description="user")

        u = user_datastore.create_user(email='admin', password=encrypt_password('admin'))
        #u2 = user_datastore.create_user(email='user', password=encrypt_password('user'))

        user_datastore.add_role_to_user(u, adminRole)

        db.session.commit()

#
#URL Declarations
#

#Returns the API key for the user
@app.route('/', methods=["GET"])
@login_required
def loginInfo():
    print current_user
    if current_user.is_authenticated:
        return json.dumps({"auth_token" : current_user.get_auth_token()})
    else:
        return {"status" : "Could Not Log In."}


#Commits Database Changes
@app.route('/save/<string:object>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def save(object):
    if object == "database" or object == "all":
        try:
            db.session.commit()
        except Exception as e:
            return json.dumps({"status" : "could not save database changes", "error" : e})

    if object == "playbook" or object == "all":
        try:
            config.savePlaybookToFile()
            config.refreshPlaybook()

            #print config.playbook.displayPlaybook()
        except Exception as e:
            return json.dumps({"status" : "could not save playbook changes", "error" : e})

    if object == "config" or object == "all":
        try:
            config.saveConfig()
            config.refreshConfig()
        except Exception as e:
            return json.dumps({"status" : "could not save config changes", "error" : e})

    return json.dumps({"status" : "changes saved"})


@app.route('/revert/<string:option>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def revert(option):
    result = []
    if option == "config" or option == "all":
        result.append(config.revert())
    if option == "playbook" or option == "all":
        result.append(config.playbook.revert())
    return json.dumps(result)

#Controls non-specific Users and Roles
@app.route('/users/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def userActions(action):
    #Adds a new user
    if action == "add":
        form = forms.NewUserForm(request.form)
        if form.validate():
            if not User.query.filter_by(email=form.username.data).first():
                un = form.username.data
                pw = encrypt_password(form.password.data)

                #Creates User
                u = user_datastore.create_user(email=un, password=pw)

                #Adds roles to the user if there are any
                if form.role.entries != [] and form.role.entries != None:
                    u.setRoles(form.role.entries)

                db.session.commit()
                return json.dumps({"status" : "user added " + str(u.id)})
            else:
                return json.dumps({"status" : "user exists"})
        else:
            return json.dumps({"status" : "invalid input"})



#Controls users and roles
@app.route('/users/<string:action>/<int:id>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def userActionsId(action, id):
    user = user_datastore.get_user(id)
    if user != None and user != []:
        #Removes a user
        if action == "remove":
            if user != current_user:
                user_datastore.delete_user(user)
                db.session.commit()
                return json.dumps({"status": "user removed"})
            else:
                return json.dumps({"status" : "user could not be removed"})

        #Edits a user
        elif action == "edit":
            form = forms.EditUserForm(request.form)
            if form.validate():
                if form.password != "":
                    verify_and_update_password(form.password.data, user)

                if form.role.entries != []:
                    user.setRoles(form.role.entries)

            return json.dumps(user.display())

        #Displays a users' information
        elif action == "display":
            if user != None:
                return json.dumps(user.display())
            else:
                return json.dumps({"status" : "could not display user"})

        return json.dumps({"status" : "user does not exist"})

#Controls non-specific Roles
@app.route('/roles/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def roleActions(action):
    #Adds a new role
    if action == "add":
        form = forms.NewRoleForm(request.form)
        if form.validate():
            query = Role.query.filter_by(name=form.name.data).first()
            if query == None:
                user_datastore.create_role(name=form.name.data, description=form.description.data)
                db.session.commit()
                return json.dumps({"status": "role added"})
            else:
                return json.dumps({"status":"role already exists"})
        else:
            return json.dumps({"status" : "could not add role, invalid input"})


#Controls the Roles
@app.route('/roles/<string:action>/<int:id>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def roleActionsId(action, id):
    role = Role.query.filter_by(id=id).first()

    if role != None and role != []:
        #Removes a role
        if action == "remove":

            #Removes role from all users before removing
            users = User.query.filter_by().all()
            for user in users:
                if user.has_role(role):
                    user_datastore.remove_role_from_user(user, role)

            #Deletes the role
            Role.query.filter_by(id=id).delete()

            db.session.commit()
            return json.dumps({"status" : "role removed"})

        #Edits a role
        elif action == "edit":
            form = forms.EditRoleForm(request.form)
            if form.validate():
                role.setDescription(form.description.data)

                db.session.commit()
                return json.dumps({"status" : "role edited"})
            else:
                return json.dumps({"status" : "invalid input"})

        #Displays a role
        elif action == "display":
            return json.dumps(role.toString())
    else:
        return json.dumps({"status" : "role not found"})


#Controls the Executioner (Start, Stop) / General Playbook Execution
execution = executionAPI.Execution()

@app.route('/execution/system/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def executionAction(action):
    response = execution.post(action)
    return jsonify(response)

#Controls the Playbook
@app.route('/playbook/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def playbookActions(action):
    if action == "display":
        pb = config.playbook.displayPlaybook()
        return json.dumps(pb)

#Controls non-specific Plays
@app.route('/playbook/play/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def playAction(action):
    if action == "add":
        form = forms.AddNewPlayForm(request.form)
        if form.validate():
            status = config.playbook.addEmptyPlay(form.name.data)
            return json.dumps(status)
        else:
            return json.dumps({"status" : "Could not add new play"})

#Controls specific plays
@app.route('/playbook/play/<string:name>/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def playActionId(name, action):
    if action == "display":
        play = config.playbook.displayPlay(name)
        if play != False:
            print play
            return str(play)
        else:
            return json.dumps({"status":"Could not display play"})

    elif action == "execute":
        play = config.playbook.getPlay(name)
        if play != None:
            return json.dumps({"results" : play.executePlay()})
        else:
            return json.dumps({"status" : "Could not execute play"})

    elif action == "remove":
        status = config.playbook.removePlay(name)
        return json.dumps(status)

#Handles Play Options
@app.route('/playbook/play/<string:name>/options/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def playOptionActions(name, action):
    if action == "display":
        play = config.playbook.displayPlayOptions(name)
        if play != False:
            return json.dumps(play)
        else:
            return json.dumps({"status":"could not display play options"})

    elif action == "edit":
        form = forms.EditPlayOptionsForm(request.form)
        if form.validate():
            autorun = form.autoRun.data
            sDT = form.s_sDT.data
            eDT = form.s_eDT.data
            interval = form.s_interval.data

            config.playbook.editPlayOptions(name, autorun, sDT, eDT, interval)

            return json.dumps({"status" : "Play options edited"})

#Controls specific Steps
@app.route('/playbook/play/<string:playName>/<string:step>/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def stepActionId(playName, step, action):
    if action == "display":
        step = config.playbook.getPlay(playName).getStep(step)
        if step != None:
            return str(step)
        else:
            return json.dumps({"status" : "could not display step"})

    elif action == "edit":
        form = forms.EditStepForm(request.form)
        if form.validate():
            id = form.id.data
            to = form.to.entries
            app = form.app.data
            device = form.device.data
            action = form.action.data
            input = form.input.data
            error = form.error.entries

            config.playbook.getPlay(playName).getStep(step).editStep(id, to, app, device, action, input, error)

            print config.playbook.getPlay(playName).getStep(step)

            return json.dumps({"status" : "Step edited"})

        return json.dumps({"status" : "Could not edit step"})

    elif action == "remove":
        return json.dumps(config.playbook.getPlay(playName).removeStep(step))

#Controls non-specific Steps
@app.route('/playbook/play/<string:playName>/steps/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def stepAction(playName, action):
    if action == "add":
        status = config.playbook.getPlay(playName).addStep()
        return json.dumps(status)


#Controls non-specific apps
@app.route('/apps/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def appActions(action):
    if action == "add":
        pass

#Controls specific apps
@app.route('/apps/<string:name>/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def appActionsId(name, action):
    if action == "display":
        try:
            form = forms.RenderArgsForm(request.form)
            path = name + "/interface/templates/" + form.page.data

            #Gets app template
            template = env.get_template(path)

            args = interface.loadApp(name, form.args.entries)

            rendered = template.render(**args)
            return json.dumps({"content" : rendered})
        except Exception as e:
            return json.dumps({"status" : "Could not display app"})

    elif action == "remove":
        pass

#Controls specific app configurations
@app.route('/apps/<string:name>/config/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def appActionsConfig(id, action):
    if action == "display":
        pass
    elif action == "edit":
        pass

#Controls the configuration
@app.route('/configuration/<string:section>/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def configActions(section, action):
    if action == "display":
        result =  json.dumps(config.displayConfig(section))
        return json.dumps(result)

    elif action == "add":
        form = forms.EditConfigForm(request.form)
        if form.validate():
            result = config.addKeyValue(section, form.key.data, form.value.data)
            print config.displayConfig(section)
            return json.dumps(result)

    elif action == "edit":
        form = forms.EditConfigForm(request.form)
        if form.validate():
            result = config.editKeyValue(section, form.key.data, form.value.data)
            print config.displayConfig(section)
            return json.dumps(result)

    elif action == "remove":
        form = forms.RemoveConfigForm(request.form)
        if form.validate():
            return config.removeConfigKey(section, form.key.data)
        else:
            return json.dumps({"status" : "Could not remove config key"})


#Controls the non-specific app device configuration
@app.route('/configuration/<string:app>/devices/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def configDevicesConfig(app, action):
    if action == "add":
        form = forms.AddNewDeviceForm(request.form)
        if form.validate():
            db.session.add(Device(name=form.name.data, app=form.app.data, username=form.username.data, password=form.pw.data, ip=form.ipaddr.data, port=form.port.data))

            db.session.commit()

            return json.dumps({"status" : "device successfully added"})
        return json.dumps({"status" : "device could not be added"})

#Controls the specific app device configuration
@app.route('/configuration/<string:app>/devices/<string:device>/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def configDevicesConfigId(app, device, action):
    if action == "display":
        query = Device.query.filter_by(app=app, name=device).first()
        if query != None and query != []:
            return str(query)
        return json.dumps({"status" : "could not display device"})

    elif action == "remove":
        query = Device.query.filter_by(app=app, name=device).first()
        if query != None and query != []:
            Device.query.filter_by(app=app, name=device).delete()

            db.session.commit()
            return json.dumps({"status" : "removed device"})
        return json.dumps({"status" : "could not remove device"})

    elif action == "edit":
        form = forms.AddNewDeviceForm(request.form)
        device = Device.query.filter_by(app=app, name=device).first()
        if form.validate() and device != None:
            #Ensures new name is unique
            if len(Device.query.filter_by(name=form.name.data).all()) > 0:
                return json.dumps({"status" : "device could not be edited"})

            device.editDevice(form)

            print Device.query.filter_by().all()
            return json.dumps({"status" : "device successfully edited"})
        return json.dumps({"status" : "device could not be edited"})



#Start Flask
def start(config_type=None):
    global db, env

    if config_type == "default":
        config.gotoDefaultConfig()



    if config.authConfig["https"].lower() == "true":
        #Sets up HTTPS
        if config.authConfig["TLS_version"] == "1.2":
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        elif config.authConfig["TLS_version"] == "1.1":
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_1)
        else:
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.load_cert_chain(config.authConfig["certificatePath"], config.authConfig["privateKeyPath"])
        logging.logger.log.send(message="Walkoff started HTTPS")
        app.run(debug=config.interfaceConfig["debug"], ssl_context=context, host=config.interfaceConfig["host"], port=int(config.interfaceConfig["port"]))
    else:
        logging.logger.log.send(message="Walkoff started HTTP")
        app.run(debug=config.interfaceConfig["debug"], host=config.interfaceConfig["host"], port=int(config.interfaceConfig["port"]))



