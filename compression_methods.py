import sys, os, re
sys.path.append(os.environ['SMART_GRID_SRC'])
from serialize_tag_date import encode_date, decode_date, \
    b64_encode_series, b64_decode_series, b64_pandas_encode_series, \
    b64_pandas_decode_series
import numpy as np
from numpy.linalg import norm
import pandas as pd
import sys
import datetime
from scipy.linalg import svd
import pywt

### Generic Functions ###

def encode_timestamp_date(d):
    return encode_date(( d.year, d.month, d.day ))

p = 0.5

### One function for each compression method ###
#     Every such function takes a data frame of the form:
#     tag/date/values... for each row, and returns
#     a vector space, one value for each row, and a reconstructed version
#     of the values matrix, after compressing/decompressing

class Compressor:
    def compress_evaluate(self, df):
        global p
        aggregate, df_compressed = self.compress(df)
        df_compressed = pd.DataFrame(df_compressed, columns=['compressed'])
        df_reconstructed = self.decompress(aggregate, df_compressed)
        aggregate = b64_encode_series(aggregate)
        err = df-df_reconstructed
        df_compressed['error'] = err.apply(norm, axis=1)
        df_compressed['space'] = df_compressed['compressed'].apply(len) + \
            len(aggregate)/float(len(df_compressed))
        n = float(len(df)) #number of data points
        df_compressed['quantile_lower'] = err.quantile(p/n, axis=1)
        df_compressed['quantile_upper'] = err.quantile(1-p/n, axis=1)

        return aggregate, df_compressed

    def serialize_compressed(self, aggregate, df_compressed, outfile=sys.stdout):
        # Print the serialized aggregate compression information.  This is
        #  the compressed data shared across the entire tag
        tag = df_compressed.index[0][0]
        outfile.write('^^^%s^%s^%s\n'%(self.name(), tag, aggregate) )
        # Print each serialized compressed tag/date
        for index, row in df_compressed.iterrows():
            tag, date = index
            date = encode_timestamp_date(date)
            outfile.write('%s^%s^%s^%s^%.5f^%.5f^%.5f^%.5f\n'%(self.name(), tag, date, 
                row['compressed'], row['space'], row['error'], row['quantile_lower'], row['quantile_upper']))

    def compress(self, df):
        ''' Returns a compressed dataframe, and another numpy array storing
            aggregate data for the entire group 
            '''
        raise NotImplementedError("Please Implement this method")

    def decompress(self, df, aggregate):
        ''' Given compressed DataFrame, produce dataframe '''
        raise NotImplementedError("Please Implement this method")
        

class ConstantPerTagCompressor(Compressor):
    def name(self):
        return 'constant_tag'
    
    def compress(self, df):
        compressed = df.ix[:,0].map(lambda row:'-')
        mean = df.mean(axis=1).mean(axis=0, dtype=np.float32)
        return np.array([mean]), compressed

    def decompress(self, aggregate, df_compressed):
        aggregate = pd.Series(aggregate*np.ones(shape=(1440,)))
        return df_compressed['compressed'].apply(lambda row:aggregate)

class ConstantPerTagDayCompressor(Compressor):
    def name(self):
        return 'constant_tag_day'
    
    def compress(self, df):
        df_compressed = pd.Series(df.mean(axis=1), dtype=np.float32)
        df_compressed = df_compressed.apply(b64_encode_series)
        return np.array([]), df_compressed

    def decompress_series(self, compressed):
        x = b64_decode_series(compressed).tolist()*1440
        return pd.Series(x,dtype=np.float32)
    
    def decompress(self, aggregate, df_compressed):
        return df_compressed['compressed'].apply(self.decompress_series)

def fill_coeffs(coeffs,coeff_lens):
    ''' Given the wavelet coefficients, fill in 0's for any but the first <levels> levels '''
    l1 = len(coeffs)
    for l in coeff_lens[l1:]:
        coeffs.append(np.zeros(l))
    return coeffs

class WaveletCompressor(Compressor):
    def name(self):
        return '%s_wavelet_%d'%(self.wavelet, self.res)
    
    def __init__(self, k, wavelet='haar'):
        self.res = k #levels of wavelets to keep
        self.wavelet = wavelet
    
    def compress_series(self, series):
        coeffs = pywt.wavedec(series.values,self.wavelet)
        coeffs_flattened = [c for l in coeffs[:self.res] for c in l]
        return b64_encode_series(np.array(coeffs_flattened, dtype=np.float32))

    def decompress_series(self, compressed):
        coeffs_flattened = b64_decode_series(compressed).tolist()
        coeff_lens = [len(c) for c in pywt.wavedec(np.zeros((1440,)),self.wavelet)]
        # unflatten coeffs_flattened using coeff_lens
        coeffs = []
        for l in coeff_lens[:self.res]:
            coeffs.append(coeffs_flattened[:l])
            coeffs_flattened = coeffs_flattened[l:]
        # Add 0's to the rest of coeffs
        coeffs = fill_coeffs(coeffs, coeff_lens)
        x = pywt.waverec(coeffs,self.wavelet)
        return pd.Series(x,dtype=np.float32)
    
    def compress(self, df):
        compressed = df.apply(self.compress_series, axis=1)
        return np.array([]), compressed

    def decompress(self, aggregate, df_compressed):
        df = df_compressed['compressed'].apply(self.decompress_series)
        return df
    
class StepCompressor(Compressor):
    def name(self):
        return 'step_%d'%(self.steps)
    
    def __init__(self, steps=10):
        self.steps = steps

    def compress_series(self, series):
        diff = series.diff()
        # 1 - s/1440 gives the proportion of series values
        #  to be kept in step function
        d = diff.quantile(1 - self.steps/1440.0)
        diff = diff.fillna(d)
        compressed = series[diff > d]
        compressed.ix[0] = series.ix[0]
        compressed.ix[1399] = series.ix[1399]
        return b64_pandas_encode_series(compressed)
        
    def decompress_series(self, compressed):
        print 'a'
        step = b64_pandas_decode_series(compressed)
        print step
        exit()
        series = pd.Series([0]*1440, dtype=np.float32)
        print 'c'
        index = series.index.tolist()
        index = [0]+index+[1440]
        for i in range(len(index)-1):
            series.ix[index[i]:index[i+1]] = step.ix[index[i+1]]
        print 'd'
        print step
        print series.ix[:10]
        print series.ix[300:350]
        print series.ix[-10:]
        exit()
        return series

    def compress(self, df):
        compressed = df.apply(self.compress_series, axis=1)
        return np.array([]), compressed
        
    def decompress(self, aggregate, df_compressed):
        print 'before'
        df = df_compressed['compressed'].apply(self.decompress_series)
        print 'after'
        exit()
        return df
#        diff = np.diff(df.values, axis=1)
#        diff = pd.DataFrame(diff, index=df.index)
#        d = diff.quantile(1 - self.steps/1440.0)
#        diff.fillna(d)
#        compressed = df[diff > d]
#        print df.shape
#        print df.ix[:5,:5]
#        exit()
#        return df

class ConstantPerTagMinuteCompressor(Compressor):
    def name(self):
        return 'constant_tag_minute'
    
    def compress(self, df):
        compressed = df.ix[:,0].map(lambda row:'-')
        mean = df.mean(axis=0).values
        return mean, compressed
        
    def decompress(self, aggregate, df_compressed):
        aggregate = pd.Series(aggregate)
        return df_compressed['compressed'].apply(lambda row:aggregate)

class SVDCompressor(Compressor):
    def name(self):
        return 'svd_%d'%self.k

    def __init__(self,k):
        ''' <k> gives the maximum number of singular vectors to use in 
            approximating the original data matrix '''
        self.k = k

    def compress(self,df):
        ''' Approximate day * minute signal using the top k eigen-vectors, 
            each of length 1440 (minutes in a day) '''
        # Matrix of signal: days * minutes
        X = df.values
        # (number of days, minutes per day)
        (n,m) = X.shape 
        # If there are only <n> days, we can't run SVD with k > n
        k = min(self.k,n)
        # Subtract off the mean from every row
        M = X.mean(axis=0)
        X2 = X - M
        # SVD
        try:
            U,s,Vh = svd(X2, full_matrices=False)
        except (np.linalg.linalg.LinAlgError, ValueError) as _:
            U = np.zeros((n,n))
            s = np.zeros((n,))
            Vh = np.zeros((n,m))
        U = U[:,:k]
        s = s[:k]
        Vh = Vh[:k,:]
        df_compressed = pd.DataFrame(U, index=df.index, dtype=np.float32)
        df_compressed = df_compressed.apply(b64_encode_series,axis=1)
        k = np.array([k],dtype=np.float32)
        return np.concatenate([M,s,Vh.flatten()]), df_compressed
    
    def decompress(self, aggregate, df_compressed):
        (n,m) = (len(df_compressed),1440)
        df2 = df_compressed['compressed'].apply(lambda s:pd.Series(b64_decode_series(s),dtype=np.float32))
        k = df2.values.shape[1]
        M = aggregate[:m]
        s = aggregate[m:(m+k)]
        Vh = np.reshape(aggregate[(m+k):], (k,m))
        reconstructed = np.dot(np.dot(df2.values,np.diag(s)),Vh) + M
        return pd.DataFrame(reconstructed,index=df_compressed.index)


### Run all compression methods ###
compressors = dict( (compressor.name(),compressor) for compressor in [
    ConstantPerTagCompressor(),
    ConstantPerTagMinuteCompressor(),
    ConstantPerTagDayCompressor(),
#    StepCompressor(),
    SVDCompressor(2),
    WaveletCompressor(4, wavelet='haar')
])

def compress_serialize_all(df, outfile=sys.stdout):
    ''' For each registered compressor, compress the given DataFrame <df>
        Serialize the compressed data, and output to <outfile> '''
    for compressor in compressors.values():
        aggregate, df_compressed = compressor.compress_evaluate(df)
        compressor.serialize_compressed(aggregate, 
            df_compressed, outfile=outfile)


def decompress_df(df_compressed, context, compressor_name):
    compressor = compressors[compressor_name]
    def decompress_group(df):
        tag = context['tag_list'][int(df.name)]
        aggregate = b64_decode_series(aggregates[tag])
        return compressor.decompress(aggregate, df)
    aggregates = context['aggregates'][compressor_name]
    df_compressed = df_compressed.xs(compressor_name, axis=1, level=0)
    df_series = df_compressed.groupby(df_compressed.index.get_level_values(0)) \
        .apply(decompress_group)
    # Delete non-integer columns
    for column in df_series.columns:
        try:
            _ = int(column)
        except:
            del df_series[column]
    df_series['tag'] = [context['tag_list'][i] 
        for i in df_compressed.index.get_level_values(0)]
    df_series['date'] = [context['date_list'][i] 
        for i in df_compressed.index.get_level_values(1)]
    df_series['date'] = df_series['date'].apply(
        lambda d: np.datetime64(datetime.date(*decode_date(d))) )
    df_series = df_series.set_index( ['tag','date']  )
    return df_series

