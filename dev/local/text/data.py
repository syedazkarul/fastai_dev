#AUTOGENERATED! DO NOT EDIT! File to edit: dev/31_text_data.ipynb (unless otherwise specified).

__all__ = ['make_vocab', 'Numericalize', 'TensorText', 'apply_coords', 'LM_Sampler', 'LM_Dataset', 'pad_collate']

from ..imports import *
from ..test import *
from ..core import *
from ..data.transform import *
from ..data.core import *
from ..data.source import *
from ..data.external import *
from ..data.pipeline import *
from .core import *
from ..notebook.showdoc import show_doc

def make_vocab(count, min_freq=3, max_vocab=60000):
    "Create a vocab of `max_vocab` size from `Counter` `count` with items present more than `min_freq`"
    vocab = [o for o,c in count.most_common(max_vocab) if c >= min_freq]
    for o in reversed(defaults.text_spec_tok): #Make sure all special tokens are in the vocab
        if o in vocab: vocab.remove(o)
        vocab.insert(0, o)
    vocab = vocab[:max_vocab]
    return vocab + ['xxfake' for _ in range(0, 8-len(vocab)%8)]

class Numericalize(ItemTransform):
    "Reversible transform of tokenized texts to numericalized ids"
    def __init__(self, vocab=None, min_freq=3, max_vocab=60000, sep=' '):
        self.vocab,self.min_freq,self.max_vocab,self.sep = vocab,min_freq,max_vocab,sep
        self.o2i = None if vocab is None else defaultdict(int, {v:k for k,v in enumerate(vocab)})

    def setup(self, dsrc):
        if dsrc is None: return
        if self.vocab is None:
            dsrc = getattr(dsrc,'train',dsrc)
            count = Counter(p for o in dsrc for p in o.split(self.sep))
            self.vocab = make_vocab(count, min_freq=self.min_freq, max_vocab=self.max_vocab)
            self.o2i = defaultdict(int, {v:k for k,v in enumerate(self.vocab) if v != 'xxfake'})

    def encodes(self, o):      return [self.o2i[o_] for o_ in o.split(self.sep)]
    def decodes(self, o)->Str: return self.sep.join([self.vocab[o_] for o_ in o if self.vocab[o_] != PAD])

from IPython.display import display, HTML

class TensorText(TensorBase):
    def get_ctxs(self, max_samples=10, **kwargs):
        n_samples = min(self.shape[0], max_samples)
        df = pd.DataFrame({'index': range(n_samples)})
        return [df.iloc[i] for i in range(n_samples)]

    def display(self, ctxs): display(HTML(pd.DataFrame(ctxs).to_html(index=False)))

def apply_coords(f, *dims):
    "Create coord array of size `dims` and apply `f` to each cell"
    gs = np.meshgrid(*map(range, dims), indexing='ij')
    return np.apply_along_axis(f, 0, np.stack(gs))

class LM_Sampler(Sampler):
    def __init__(self, ds): self.ds,self.bs,self.spb = ds,ds.bs,len(ds)//ds.bs
    def __len__(self): return len(self.ds)
    def __iter__(self): return ((i%self.bs)*self.spb + (i//self.bs) for i in L.range(self.ds))

class LM_Dataset(BaseDS):
    def __init__(self, ds, lens=None, bs=64, seq_len=72, shuffle=False, cache=2, as_tensor=True):
        super().__init__(ReindexCollection(ds, cache=cache))
        self.bs,self.seq_len,self.shuffle,self.as_tensor = bs,seq_len,shuffle,as_tensor
        if lens is None: lens = [len(o[0]) for o in ds]
        self.lens = ReindexCollection(lens, idxs=self.ds.idxs)
        # The "-1" is to allow for final label
        self.n = round_multiple(sum(lens)-1, bs*seq_len, round_down=True)
        self.reset()

    def __len__(self): return self.n//(self.seq_len)
    def reset(self):
        if self.shuffle: self.ds.shuffle()
        self.cum_lens = np.cumsum(self.lens)

    def __getitem__(self, seq):
        def _f(xy,it):
            tokidx = seq*self.seq_len + xy + it
            docidx = np.searchsorted(self.cum_lens, tokidx+1)
            return self.ds[docidx][0][tokidx-self.cum_lens[docidx]]
        res = [[_f(xy,it) for it in range(self.seq_len)] for xy in range(2)]
        return tuple(TensorText(tensor(o)) if self.as_tensor else o for o in res)

def pad_collate(samples, pad_idx=1, pad_first=True, backwards=False):
    "Function that collect samples and adds padding. Flips token order if needed"
    max_len = max([len(s[0]) for s in samples])
    res = torch.zeros(len(samples), max_len).long() + pad_idx
    if backwards: pad_first = not pad_first
    for i,s in enumerate(samples):
        sl = slice(-len(s[0]), sys.maxsize) if pad_first else slice(0, len(s[0]))
        res[i,sl] = LongTensor(s[0])
    if backwards: res = res.flip(1)
    return TensorText(res), tensor(np.array([s[1] for s in samples]))