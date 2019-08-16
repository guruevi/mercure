#!/usr/bin/python

# Standard python includes
import uvicorn
import os
import asyncio
import datetime
import logging

# 3rd party
import daiquiri
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.responses import PlainTextResponse
from starlette.responses import JSONResponse
from starlette.responses import RedirectResponse
from starlette.background import BackgroundTasks
from starlette.config import Config
from starlette.datastructures import URL, Secret
import databases
import sqlalchemy
 
# App-specific includes
import common.monitor as monitor

hermes_bookkeeper_version = "0.1a"


###################################################################################
## Configuration and initialization
###################################################################################

daiquiri.setup(
    level=logging.INFO,
    outputs=(
        daiquiri.output.Stream(
            formatter=daiquiri.formatter.ColorFormatter(
                fmt="%(color)s%(levelname)-8.8s "
                "%(name)s: %(message)s%(color_stop)s"
            )
        ),
    ),
)
logger = daiquiri.getLogger("bookkeeper")


bookkeeper_config = Config("configuration/bookkeeper.env")
BOOKKEEPER_PORT   = bookkeeper_config('PORT', cast=int, default=8080)
BOOKKEEPER_HOST   = bookkeeper_config('HOST', default='0.0.0.0')
DATABASE_URL      = bookkeeper_config('DATABASE_URL')

database = databases.Database(DATABASE_URL)
app = Starlette(debug=True)


###################################################################################
## Definition of database tables
###################################################################################

metadata = sqlalchemy.MetaData()
engine = sqlalchemy.create_engine(DATABASE_URL)
connection = None

hermes_events = sqlalchemy.Table(
    "hermes_events",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True, autoincrement=True),
    sqlalchemy.Column("time", sqlalchemy.DateTime),
    sqlalchemy.Column("sender", sqlalchemy.String, default="Unknown"),
    sqlalchemy.Column("event", sqlalchemy.String, default=monitor.h_events.UKNOWN),
    sqlalchemy.Column("severity", sqlalchemy.Integer, default=monitor.severity.INFO),
    sqlalchemy.Column("description", sqlalchemy.String, default="")
)

webgui_events = sqlalchemy.Table(
    "webgui_events",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True, autoincrement=True),
    sqlalchemy.Column("time", sqlalchemy.DateTime),
    sqlalchemy.Column("sender", sqlalchemy.String, default="Unknown"),
    sqlalchemy.Column("event", sqlalchemy.String, default=monitor.w_events.UKNOWN),
    sqlalchemy.Column("user", sqlalchemy.String, default=""),
    sqlalchemy.Column("description", sqlalchemy.String, default="")
)

dicom_file = sqlalchemy.Table(
    "dicom_file",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True, autoincrement=True),
    sqlalchemy.Column("time", sqlalchemy.DateTime),
    sqlalchemy.Column("filename", sqlalchemy.String),
    sqlalchemy.Column("file_uid", sqlalchemy.String),
    sqlalchemy.Column("series_uid", sqlalchemy.String)
)

dicom_series = sqlalchemy.Table(
    "dicom_series",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True, autoincrement=True),
    sqlalchemy.Column("time", sqlalchemy.DateTime),
    sqlalchemy.Column("series_uid", sqlalchemy.String),
    sqlalchemy.Column("tag_patienname", sqlalchemy.String),
    sqlalchemy.Column("tag_patientid", sqlalchemy.String),
    sqlalchemy.Column("tag_accessionnumber", sqlalchemy.String),
    sqlalchemy.Column("tag_seriesnumber", sqlalchemy.String),    
    sqlalchemy.Column("tag_studyid", sqlalchemy.String),
    sqlalchemy.Column("tag_patientbirthdate", sqlalchemy.String),
    sqlalchemy.Column("tag_patientsex", sqlalchemy.String),
    sqlalchemy.Column("tag_acquisitiondate", sqlalchemy.String),
    sqlalchemy.Column("tag_acquisitiontime", sqlalchemy.String),
    sqlalchemy.Column("tag_modality", sqlalchemy.String),
    sqlalchemy.Column("tag_bodypartexamined", sqlalchemy.String),
    sqlalchemy.Column("tag_studydescription", sqlalchemy.String),
    sqlalchemy.Column("tag_seriesdescription", sqlalchemy.String),    
    sqlalchemy.Column("tag_protocolname", sqlalchemy.String),
    sqlalchemy.Column("tag_codevalue", sqlalchemy.String),
    sqlalchemy.Column("tag_codemeaning", sqlalchemy.String),
    sqlalchemy.Column("tag_sequencename", sqlalchemy.String),
    sqlalchemy.Column("tag_scanningsequence", sqlalchemy.String),
    sqlalchemy.Column("tag_sequencevariant", sqlalchemy.String),
    sqlalchemy.Column("tag_slicethickness", sqlalchemy.String),
    sqlalchemy.Column("tag_contrastbolusagent", sqlalchemy.String),
    sqlalchemy.Column("tag_referringphysicianname", sqlalchemy.String),    
    sqlalchemy.Column("tag_manufacturer", sqlalchemy.String),
    sqlalchemy.Column("tag_manufacturermodelname", sqlalchemy.String),
    sqlalchemy.Column("tag_magneticfieldstrength", sqlalchemy.String),
    sqlalchemy.Column("tag_deviceserialnumber", sqlalchemy.String),    
    sqlalchemy.Column("tag_softwareversions", sqlalchemy.String),
    sqlalchemy.Column("tag_stationname", sqlalchemy.String)
)

dicom_series_map = sqlalchemy.Table(
    "dicom_series_map",
    metadata,
    sqlalchemy.Column("file_id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("series_id", sqlalchemy.Integer)
)

file_event = sqlalchemy.Table(
    "file_event",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True, autoincrement=True),
    sqlalchemy.Column("time", sqlalchemy.DateTime),
    sqlalchemy.Column("dicom_file", sqlalchemy.Integer),
    sqlalchemy.Column("event", sqlalchemy.Integer)
)

series_event = sqlalchemy.Table(
    "series_event",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True, autoincrement=True),
    sqlalchemy.Column("time", sqlalchemy.DateTime),
    sqlalchemy.Column("dicom_series", sqlalchemy.Integer),
    sqlalchemy.Column("event", sqlalchemy.Integer),
    sqlalchemy.Column("source", sqlalchemy.String),
    sqlalchemy.Column("target", sqlalchemy.String),
    sqlalchemy.Column("file_count", sqlalchemy.Integer)
)


###################################################################################
## Event handlers
###################################################################################

def create_database():
    metadata.create_all(engine)


@app.on_event("startup")
async def startup():
    #await database.connect()
    global connection
    connection = engine.connect()
    create_database()


@app.on_event("shutdown")
async def shutdown():
    #await database.disconnect()
    engine.disconnect()


###################################################################################
## Endpoints
###################################################################################

async def execute_db_operation(operation):
    connection.execute(operation)
    

@app.route('/test', methods=["GET","POST"])
async def test_endpoint(request):
    return JSONResponse({'ok': ''})


@app.route('/hermes-event', methods=["POST"])
async def post_hermes_event(request):
    sender=request.query_params.get("sender","Unknown")
    event=request.query_params.get("event",monitor.h_events.UKNOWN)
    severity=int(request.query_params.get("severity",monitor.severity.INFO))    
    description=request.query_params.get("description","")       

    query = hermes_events.insert().values(
        sender=sender, event=event, severity=severity, description=description, time=datetime.datetime.now()
    )
    tasks = BackgroundTasks()
    tasks.add_task(execute_db_operation, operation=query)
    return JSONResponse({'ok': ''}, background=tasks)


@app.route('/webgui-event', methods=["POST"])
async def post_webgui_event(request):
    sender=request.query_params.get("sender","Unknown")
    event=request.query_params.get("event",monitor.w_events.UKNOWN)
    user=request.query_params.get("user","UNKNOWN")
    description=request.query_params.get("description","")       

    query = webgui_events.insert().values(
        sender=sender, event=event, user=user, description=description, time=datetime.datetime.now()
    )
    tasks = BackgroundTasks()
    tasks.add_task(execute_db_operation, operation=query)
    return JSONResponse({'ok': ''}, background=tasks)


@app.route('/register-dicom', methods=["POST"])
async def register_dicom(request):
    form = await request.form()
    filename  =form.get("filename","")
    file_uid  =form.get("file_uid","")
    series_uid=form.get("series_uid","")

    query = dicom_file.insert().values(
        filename=filename, file_uid=file_uid, series_uid=series_uid, time=datetime.datetime.now()
    )
    tasks = BackgroundTasks()
    tasks.add_task(execute_db_operation, operation=query)    
    return JSONResponse({'ok': ''}, background=tasks)


@app.route('/register-series', methods=["POST"])
async def register_series(request):
    form = await request.form()

    query = dicom_series.insert().values(
        time=datetime.datetime.now(), series_uid=form.get("series_uid",""),
        tag_patienname=form.get("tag_patienname","")
    )
    tasks = BackgroundTasks()
    tasks.add_task(execute_db_operation, operation=query)    
    return JSONResponse({'ok': ''}, background=tasks)

#    sqlalchemy.Column("tag_patienname", sqlalchemy.String),
#    sqlalchemy.Column("tag_patientid", sqlalchemy.String),
#    sqlalchemy.Column("tag_accessionnumber", sqlalchemy.String),
#    sqlalchemy.Column("tag_seriesnumber", sqlalchemy.String),    
#    sqlalchemy.Column("tag_studyid", sqlalchemy.String),
#    sqlalchemy.Column("tag_patientbirthdate", sqlalchemy.String),
#    sqlalchemy.Column("tag_patientsex", sqlalchemy.String),
#    sqlalchemy.Column("tag_acquisitiondate", sqlalchemy.String),
#    sqlalchemy.Column("tag_acquisitiontime", sqlalchemy.String),
#    sqlalchemy.Column("tag_modality", sqlalchemy.String),
#    sqlalchemy.Column("tag_bodypartexamined", sqlalchemy.String),
#    sqlalchemy.Column("tag_studydescription", sqlalchemy.String),
#    sqlalchemy.Column("tag_seriesdescription", sqlalchemy.String),    
#    sqlalchemy.Column("tag_protocolname", sqlalchemy.String),
#    sqlalchemy.Column("tag_codevalue", sqlalchemy.String),
#    sqlalchemy.Column("tag_codemeaning", sqlalchemy.String),
#    sqlalchemy.Column("tag_sequencename", sqlalchemy.String),
#    sqlalchemy.Column("tag_scanningsequence", sqlalchemy.String),
#    sqlalchemy.Column("tag_sequencevariant", sqlalchemy.String),
#    sqlalchemy.Column("tag_slicethickness", sqlalchemy.String),
#    sqlalchemy.Column("tag_contrastbolusagent", sqlalchemy.String),
#    sqlalchemy.Column("tag_referringphysicianname", sqlalchemy.String),    
#    sqlalchemy.Column("tag_manufacturer", sqlalchemy.String),
#    sqlalchemy.Column("tag_manufacturermodelname", sqlalchemy.String),
#    sqlalchemy.Column("tag_magneticfieldstrength", sqlalchemy.String),
#    sqlalchemy.Column("tag_deviceserialnumber", sqlalchemy.String),    
#    sqlalchemy.Column("tag_softwareversions", sqlalchemy.String),
#    sqlalchemy.Column("tag_stationname", sqlalchemy.String)



###################################################################################
## Main entry function
###################################################################################

if __name__ == '__main__':
    logger.info("")
    logger.info(f"Hermes Bookkeeper ver {hermes_bookkeeper_version}")
    logger.info("----------------------------")
    logger.info("")

    uvicorn.run(app, host=BOOKKEEPER_HOST, port=BOOKKEEPER_PORT)
