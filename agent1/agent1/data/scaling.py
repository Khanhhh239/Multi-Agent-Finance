"""Lấy mẫu hàng lồng nhau, ghi liên tiếp và đọc theo lô cho LightGBM."""
import json
from pathlib import Path
import numpy as np
import lightgbm as lgb


class MemmapSequence(lgb.Sequence):
    batch_size=8192

    def __init__(self,path,rows,columns):
        self.data=np.memmap(path,dtype='float32',mode='r',shape=(rows,columns))

    def __len__(self):return len(self.data)

    def __getitem__(self,index):
        # LightGBM dùng float64 cho mẫu xây bin; chỉ chuyển batch đang đọc.
        return np.asarray(self.data[index],dtype='float64')


class NestedRowWriter:
    def __init__(self,directory,sizes,total,columns,seed=7):
        self.sizes=sorted(set(map(int,sizes)))
        if not self.sizes or self.sizes[0]<=0 or self.sizes[-1]>total or columns<=0:
            raise ValueError('Kích cỡ mẫu phải dương và không vượt số hàng thật')
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.total_left=int(total);self.keep_left=self.sizes[-1];self.selected=0;self.columns=columns
        self.rng=np.random.default_rng(seed)
        self.ranks=np.random.default_rng(np.random.SeedSequence([seed,1])).permutation(self.keep_left)
        self.X={n:np.memmap(self.directory/f'X_{n}.dat',dtype='float32',mode='w+',shape=(n,columns)) for n in self.sizes}
        self.y={n:np.memmap(self.directory/f'y_{n}.dat',dtype='float32',mode='w+',shape=(n,)) for n in self.sizes}
        self.offsets={n:0 for n in self.sizes}
        self.groups={n:set() for n in self.sizes}

    def append(self,X,y,groups=None):
        X,y=np.asarray(X),np.asarray(y)
        if X.ndim!=2 or X.shape[1]!=self.columns or y.shape!=(len(X),) or len(X)>self.total_left:
            raise ValueError('Batch không khớp lược đồ hoặc tổng số hàng')
        count=int(self.rng.hypergeometric(self.keep_left,self.total_left-self.keep_left,len(X))) if len(X) else 0
        chosen=np.sort(self.rng.choice(len(X),count,replace=False))
        ranks=self.ranks[self.selected:self.selected+count]
        for n in self.sizes:
            take=chosen[ranks<n];start=self.offsets[n];end=start+len(take)
            self.X[n][start:end]=X[take];self.y[n][start:end]=y[take];self.offsets[n]=end
            if groups is not None:self.groups[n].update(np.asarray(groups)[take].tolist())
        self.total_left-=len(X);self.keep_left-=count;self.selected+=count

    def finish(self,metadata=None):
        if self.total_left or self.keep_left or any(self.offsets[n]!=n for n in self.sizes):
            raise ValueError('Chưa ghi đủ dữ liệu; không phát manifest hoàn tất')
        for array in [*self.X.values(),*self.y.values()]:array.flush()
        result=dict(metadata or {},sizes=self.sizes,columns=self.columns,rows_written=self.offsets,
            sampling='uniform nested row subsets; generation order preserved',complete=True,
            n_firms_used={n:len(self.groups[n]) for n in self.sizes})
        (self.directory/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        self.X.clear();self.y.clear()
        return result
