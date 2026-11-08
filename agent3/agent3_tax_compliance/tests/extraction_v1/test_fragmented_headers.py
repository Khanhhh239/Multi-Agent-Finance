"""Regression: bilingual PDF font spans must preserve roles and source evidence."""
import unittest

from test_extraction import document, MASTER
from src.adapters.ocr.protocol import ExtractionBlock, BlockOrigin
from src.domain.evidence import Evidence
from src.extraction.service import extract


def fragmented(spans):
    doc=document();blocks=[]
    for i,(text,x,y,width) in enumerate(spans):
        identifier='span-'+str(i)
        blocks.append(ExtractionBlock(block_id=identifier,text_raw=text,reading_order=i,
            geometry_status='AVAILABLE',origins=(BlockOrigin(method='NATIVE_TEXT',source_block_id=identifier),),
            evidence=Evidence(source_id=doc.source_id,document_id=doc.document_id,page_index=0,
                bbox=(x,y,x+width,y+.012),block_id=identifier,transform_id='transform-0')))
    return doc.model_copy(update={'pages':(doc.pages[0].model_copy(update={'blocks':tuple(blocks)}),)})


class FragmentedHeadersTests(unittest.TestCase):
    def test_bilingual_roles_next_line_name_and_original_evidence(self):
        # English font starts slightly lower; source order puts ':' first.
        doc=fragmented([
            ('Tên người bán',.07,.10,.08),(':',.185,.10,.004),('(Seller)',.15,.102,.035),
            ('CÔNG TY TEST (VIỆT NAM)',.07,.116,.36),
            ('Mã số thuế',.07,.14,.065),(':',.181,.14,.004),('(Tax code)',.135,.142,.046),
            ('1234567890-001',.195,.14,.11),
            ('Tên người mua',.07,.20,.085),('(Buyer)',.155,.202,.035),(':',.19,.20,.004),
            ('CÔNG TY B',.20,.20,.20),
            ('Mã số thuế',.07,.23,.065),('(Tax code)',.135,.232,.046),(':',.181,.23,.004),
            ('9876543210',.195,.23,.10),
            ('Địa chỉ',.07,.26,.045),('(Address)',.115,.262,.05),(':',.165,.26,.004),
            ('Địa chỉ B',.18,.26,.20),
        ])
        record=extract(doc,'PDF',MASTER).record
        self.assertEqual(record.parties.seller.name.value,'CÔNG TY TEST (VIỆT NAM)')
        self.assertEqual(record.parties.seller.tax_id.value,'1234567890001')
        self.assertEqual(record.parties.buyer.name.value,'CÔNG TY B')
        self.assertEqual(record.parties.buyer.tax_id.value,'9876543210')
        self.assertEqual(record.parties.buyer.address.value,'Địa chỉ B')
        self.assertEqual({e.block_id for e in record.parties.seller.name.provenance.evidence},
                         {'span-0','span-1','span-2','span-3'})

    def test_header_date_number_totals_and_explicit_locale(self):
        from src.extraction.contracts import ExtractionProfile
        doc=fragmented([
            ('Số',.60,.10,.02),('(No.)',.625,.102,.03),(':',.655,.10,.005),('1234567',.67,.10,.08),
            ('Ngày (Date) 02 Tháng (Month) 12 Năm (Year) 2023',.2,.14,.6),
            ('Đồng tiền thanh toán (Payment currency): VND',.4,.2,.5),
            ('Cộng tiền hàng',.50,.4,.12),('(Total amount)',.62,.4,.10),(':',.72,.4,.005),('20.089',.88,.401,.06),
            ('Tiền thuế GTGT (VAT amount):',.5,.43,.22),('2.009',.88,.431,.06),
            ('Tổng cộng tiền thanh toán (Total payment):',.4,.46,.32),('22.098',.88,.461,.06),
            ('KÝ NGÀY: 03/12/2023 10:35:34',.5,.6,.4),
        ])
        record=extract(doc,'PDF',MASTER,ExtractionProfile(number_locale='VI')).record
        self.assertEqual(record.invoice.number.value,'1234567')
        self.assertEqual(record.invoice.issue_date.value.isoformat(),'2023-12-02')
        self.assertEqual(record.currency.value,'VND')
        self.assertEqual(tuple(str(getattr(record.totals,n).value) for n in ('net','vat','gross')),('20089','2009','22098'))
        auto=extract(doc,'PDF',MASTER).record
        self.assertEqual(auto.totals.gross.status,'AMBIGUOUS')

    def test_name_does_not_consume_next_field_or_distant_text(self):
        for text,y in [('Mã số thuế (Tax code): 1234567890',.116),('Unrelated company',.25)]:
            record=extract(fragmented([('Tên người bán (Seller):',.07,.10,.2),(text,.07,y,.5)]),'PDF',MASTER).record
            self.assertEqual(record.parties.seller.name.status,'MISSING')


if __name__=='__main__': unittest.main()
