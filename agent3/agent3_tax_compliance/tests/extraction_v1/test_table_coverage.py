import unittest
from test_fragmented_headers import fragmented
from test_extraction import MASTER
from src.extraction.service import extract
from src.extraction.contracts import ExtractionProfile


def table(y,name='Dịch vụ A'):
    return [('STT',.04,y,.04),('Tên hàng hóa, dịch vụ',.15,y,.26),('Số lượng',.5,y,.1),
            ('Thành tiền',.8,y,.12),('1',.04,y+.05,.02),(name,.15,y+.05,.25),
            ('1',.5,y+.05,.03),('10.000',.8,y+.05,.12)]


class TableCoverageTests(unittest.TestCase):
    def test_repeated_headers_on_one_page_are_distinct_tables(self):
        doc=fragmented(table(.2)+[('Cộng tiền hàng:',.15,.3,.3),('10.000',.8,.3,.12)]+table(.5,'Dịch vụ B'))
        a=extract(doc,'PDF',MASTER,ExtractionProfile(number_locale='VI'))
        self.assertEqual([i.description.value for i in a.record.items],['Dịch vụ A','Dịch vụ B'])
        self.assertEqual(len({i.item_id for i in a.record.items}),2)
        self.assertNotEqual(a.record.item_discovery_status,'COMPLETE')

    def continuation(self,label):
        doc=fragmented(table(.2));second=fragmented([(label,.1,.05,.3),('2',.04,.1,.02),
            ('Dịch vụ B',.15,.1,.25),('2',.5,.1,.03),('20.000',.8,.1,.12),('Tổng cộng:',.15,.2,.3)])
        p=second.pages[0]
        blocks=tuple(b.model_copy(update={'block_id':'p2-'+b.block_id,'evidence':b.evidence.model_copy(update={'page_index':1,'block_id':'p2-'+b.block_id})}) for b in p.blocks)
        return doc.model_copy(update={'pages':(doc.pages[0],p.model_copy(update={'page_index':1,'page_id':'page-2','blocks':blocks}))})

    def test_explicit_continuation_can_reuse_columns_but_never_completeness(self):
        a=extract(self.continuation('Tiếp theo'),'PDF',MASTER,ExtractionProfile(number_locale='VI'))
        self.assertEqual(len(a.record.items),2)
        self.assertEqual(a.record.items[1].description.value,'Dịch vụ B')
        self.assertTrue(all(e.page_index==1 for e in a.record.items[1].net.provenance.evidence))
        self.assertNotEqual(a.record.item_discovery_status,'COMPLETE')
        self.assertTrue(any(i.code=='CONTINUATION_LAYOUT_REVIEW' for i in a.issues))

    def test_unlabelled_next_page_is_not_guessed_as_continuation(self):
        a=extract(self.continuation('Tài liệu khác'),'PDF',MASTER,ExtractionProfile(number_locale='VI'))
        self.assertEqual(len(a.record.items),1)


if __name__=='__main__':unittest.main()
