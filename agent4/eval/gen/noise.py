import re
import unicodedata


def perturb(question,index):
    kind=('noaccent','colloquial','abbreviation','typo','ordinal')[index%5]
    if kind=='noaccent':
        question=''.join(c for c in unicodedata.normalize('NFD',question.replace('đ','d').replace('Đ','D')) if unicodedata.category(c)!='Mn')
    elif kind=='colloquial':question='Cho anh coi với, '+question
    elif kind=='abbreviation':
        original=question
        for phrase,short in [('doanh thu','dt'),('chi phí','cp'),('lợi nhuận','ln')]:
            question=re.sub(phrase,short,question,flags=re.I)
        if original==question:question='Nhờ tra giúp: '+question;kind='colloquial'
    elif kind=='typo':
        match=re.search(r'[^\W\d_]{5,}',question)
        if match:
            word=match.group();word=word[:1]+word[2]+word[1]+word[3:]
            question=question[:match.start()]+word+question[match.end():]
        else:question+=' giùm nhé';kind='colloquial'
    else:question='Yêu cầu số 17: '+question
    return question,kind

