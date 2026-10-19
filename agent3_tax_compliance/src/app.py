"""Foundation app factory. No DB connection, model or secret lookup on import."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(title='Capture foundation', version='1.0.0')
    application.state.settings = settings or Settings.from_env()
    from .ingestion.api import router
    from .ingestion.models import IngestionError
    application.include_router(router)
    from .adapters.ocr.api import router as ocr_router
    application.include_router(ocr_router)
    from .extraction.api import router as extraction_router
    application.include_router(extraction_router)
    from .quality.api import router as quality_router
    application.include_router(quality_router)
    from .review.api import router as review_router
    from .review.contracts import ReviewError
    application.include_router(review_router)
    from .planning.api import router as planning_router
    application.include_router(planning_router)
    from .rules.api import router as rules_router
    application.include_router(rules_router)
    from .api.v1.evaluations import router as evaluations_router
    from .api.v1.rule_results import router as results_router
    application.include_router(evaluations_router)
    application.include_router(results_router)
    from .explanation_v2.api import router as explanation_router
    application.include_router(explanation_router)
    from .business_review.api import router as business_router
    application.include_router(business_router)
    from .recovery.api import router as recovery_router
    application.include_router(recovery_router)

    @application.middleware('http')
    async def private_capture_responses(request,call_next):
        response=await call_next(request)
        if request.url.path.startswith('/v1/') and request.url.path!='/v1/health':
            response.headers['Cache-Control']='private, no-store'
        return response

    @application.exception_handler(ReviewError)
    async def review_error(request,error):
        return JSONResponse(status_code=error.status,content={'schema_version':'1.0.0','error':{
            'code':error.code,'message':error.message,'latest_revision':error.latest_revision}})

    @application.exception_handler(KeyError)
    async def missing(request,error):
        return JSONResponse(status_code=404,content={'schema_version':'1.0.0','error':{'code':'NOT_FOUND','message':'Resource not found in this scope.'}})

    @application.exception_handler(ValueError)
    async def invalid(request,error):
        return JSONResponse(status_code=422,content={'schema_version':'1.0.0','error':{'code':'INVALID_DATA','message':'Data violates the capture contract; check field formats and source integrity.'}})

    @application.exception_handler(IngestionError)
    async def ingestion_error(request,error):
        headers={'WWW-Authenticate':'Bearer'} if error.status==401 else None
        return JSONResponse(status_code=error.status,content={'schema_version':'1.0.0','error':error.issue.model_dump(mode='json')},headers=headers)

    @application.exception_handler(PermissionError)
    async def denied(request,error):
        return JSONResponse(status_code=403,content={'schema_version':'1.0.0','error':{
            'code':'ACCESS_DENIED','retryable':False,'message':'Access denied.','next_action':'Use an authorized taxpayer scope.'}})

    @application.get('/v1/health')
    def health():
        return {'schema_version': '1.0.0', 'status': 'ok', 'stage': 'foundation'}

    return application
