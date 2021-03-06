import matplotlib.pyplot as plt
import random
import numpy as np

def sample_df(df, samples):
    ''' Samples rows of a dataframe '''
    rows = random.sample(df.index, samples)
    return df.ix[rows]

def plot_daily_series(df, samples=5, title=None, ylim=None):
    ''' Given a dataframe containing daily series for sensors, 
        randomly sample <samples> days, and plot the daily variation for those days'''
    if not samples is None:
        df = sample_df(df, samples)
    plt.clf()
    X = df.copy()
    # Find the minimum and maximum
    ymax = X.max().max()
    ymin = X.min().min()
    yrange = ymax - ymin
    fig = plt.figure(figsize=(15,5))
    ax = fig.add_subplot(221)
    fig.suptitle('yrange: %.5f'%yrange)
    if yrange == 0:
        yrange = 1
    #Add a small amount of random noise, so we can see overlapping lines
    X.index = X.index.droplevel(0)
    X.T.plot(ax=ax, grid=False, legend=False, title=title)
    ax.legend(loc='center left', bbox_to_anchor=(1,0.5), fancybox=True, shadow=True)
    # Set reasonable x/y limits.  y slightly above/below the largest values
    plt.xlim([0,1440])
    if ylim is None:
        if yrange == 0:
            ymax, ymin = (-1,1)
        else:
            ymax += 0.1*yrange
            ymin -= 0.1*yrange
        ylim = [ymin, ymax]  
    plt.ylim(ylim)
    plt.show()
