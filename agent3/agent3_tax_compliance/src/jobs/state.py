from ..review.contracts import ReviewError

TRANSITIONS={
 'QUEUED':{'PREPARING','WAITING_DATA','OPERATOR'},
 'PREPARING':{'EXTRACTING','PROCESSING_ERROR'},
 'EXTRACTING':{'ASSESSING','PROCESSING_ERROR'},
 'ASSESSING':{'REVIEW','PROCESSING_ERROR'},
 'REVIEW':{'COMPLETED','WAITING_DATA','OPERATOR'},
 'PROCESSING_ERROR':{'QUEUED','WAITING_DATA','OPERATOR'},
 'WAITING_DATA':{'OPERATOR'},'OPERATOR':set(),'COMPLETED':set(),
}
def validate_transition(before,after):
    if after not in TRANSITIONS.get(before,set()):
        raise ReviewError('INVALID_TRANSITION','Invalid capture job transition.',409)

