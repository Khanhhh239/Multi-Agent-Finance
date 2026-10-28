from decimal import Decimal
import unittest
import test_regions
from src.recovery.line_regions import line_regions,region_box
from src.recovery.regions import plan_regions
from src.recovery.policy import diagnose,select_candidate


class Round3RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.case=test_regions.RegionTests('test_reread_is_cached_candidate_with_original_and_transform');self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_word_spans_are_grouped_without_replacing_source_evidence(self):
        case=self.case;page=case.normalized.pages[0];template=page.blocks[0];blocks=[]
        for i in range(8):
            identifier='word-'+str(i);e=template.evidence.model_copy(update={'block_id':identifier,'bbox':(.1+i*.04,.2,.13+i*.04,.215)})
            blocks.append(template.model_copy(update={'block_id':identifier,'text_raw':'word'+str(i),'evidence':e}))
        grouped=line_regions([(page,b) for b in blocks])
        self.assertEqual(len(grouped),1)
        self.assertEqual(grouped[0][1].source_blocks,tuple(blocks))
        self.assertEqual(grouped[0][1].evidence,blocks[0].evidence)
        self.assertGreater(region_box(grouped[0][1])[2],blocks[0].evidence.bbox[2])
        record=case.f.record;name=record.parties.buyer.name
        name=name.model_copy(update={'provenance':name.provenance.model_copy(update={'evidence':tuple(b.evidence for b in blocks)})})
        buyer=record.parties.buyer.model_copy(update={'name':name})
        record=record.model_copy(update={'parties':record.parties.model_copy(update={'buyer':buyer})})
        document=case.normalized.model_copy(update={'pages':(page.model_copy(update={'blocks':tuple(blocks)}),)})
        _,regions=plan_regions(record,case.f.artifact,document,'parties.buyer.name')
        self.assertEqual(len(regions),1);self.assertEqual(len(regions[0][1].source_blocks),8)

    def test_present_numeric_name_is_flagged_but_not_selected(self):
        case=self.case;record=case.f.record;buyer=record.parties.buyer
        field=buyer.name.model_copy(update={'value':'300'})
        record=record.model_copy(update={'parties':record.parties.model_copy(update={'buyer':buyer.model_copy(update={'name':field})})})
        plan=diagnose(record,case.f.artifact,case.normalized)
        entry=next(e for e in plan['entries'] if e['field_path']=='parties.buyer.name')
        self.assertIn('NONALPHABETIC_NAME',entry['issue_codes'])
        self.assertEqual(select_candidate(field,entry,{'status':'CANDIDATE','suggested_value':'CÔNG TY B'})['decision'],'REVIEW')

    def test_arithmetic_mismatch_only_schedules_review(self):
        case=self.case;record=case.f.record;totals=record.totals
        changed=totals.gross.model_copy(update={'value':Decimal('999')})
        record=record.model_copy(update={'totals':totals.model_copy(update={'gross':changed})})
        plan=diagnose(record,case.f.artifact,case.normalized)
        suspicious=[e for e in plan['entries'] if 'TOTAL_ARITHMETIC_MISMATCH' in e['issue_codes']]
        self.assertEqual(len(suspicious),3);self.assertLessEqual(plan['scheduled_fields'],2);self.assertLessEqual(plan['scheduled_crops'],4)
        self.assertEqual(record.totals.gross.value,Decimal('999'))
