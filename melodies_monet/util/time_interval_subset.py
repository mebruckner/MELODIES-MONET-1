def subset_model_filelist(all_files,timeformat,timestep,timeinterval):
    '''Subset model filelist to within a given time interval
    '''
    import pandas as pd
    subset_interval = pd.date_range(start=timeinterval[0],end=timeinterval[-1],freq=timestep)
    interval_files = []
    for i in subset_interval:
        flst = [fs for fs in all_files if i.strftime(timeformat) in fs]
        if len(flst) == 1:
            interval_files.append(flst[0])
        elif len(flst) >1:
            print('More than 1 file for {} in listing'.format(i.strftime(timeformat)))
    return interval_files

def subset_OMPS_l2(all_files,timeinterval):
    import pandas as pd
    interval_files = []
    subset_interval = pd.date_range(start=timeinterval[0],end=timeinterval[-1],freq='D')
    
    for i in subset_interval:
        fst = [fs for fs in all_files if 'OMPS-NPP_NMTO3-L2_v2.1_{}'.format(i.strftime('%Ym%m%d')) in fs]
        for j in fst:
            interval_files.append(j)
    return interval_files