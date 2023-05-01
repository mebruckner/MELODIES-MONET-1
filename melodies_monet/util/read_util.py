# Copyright (C) 2022 National Center for Atmospheric Research and National Oceanic and Atmospheric Administration
# SPDX-License-Identifier: Apache-2.0
#
def read_saved_data(analysis, filenames, method, attr, xr_kws={}):
    """Read previously saved dict containing melodies-monet data (:attr:`paired`, :attr:`models`, or :attr:`obs`)
    from pickle file or netcdf file, populating the :attr:`paired`, :attr:`models`, or :attr:`obs` dict.

    Parameters
    ----------
    analysis : class
        Instance of the analysis class from driver script.
    filenames : str or iterable
        str or list for reading in pkl. For netCDF, must be dict with format {group1:str or iterable of filenames, group2:...}
    method : str
        One of either 'pkl' or 'netcdf'.
    attr : str
        The analysis attribute that will be populated with the saved data. One of either 'paired' or 'models' or 'obs'.
    **kwargs : optional
        Additional keyword arguments for xr.open_dataset()

    Returns
    -------
    None
    """
    import xarray as xr
    from glob import glob
    import os
    
    # Determine where to read files from
    if getattr(analysis,'output_dir_read') is not None:
        read_dir = getattr(analysis,'output_dir_read')
    else:
        read_dir = ''
    
    # expand any wildcards in the filenames
    if method=='pkl':
        if isinstance(filenames,str):
            files = sorted([file for sublist in [glob(os.path.join(read_dir,file)) for file in [filenames]] for file in sublist])
        else:
            files = sorted([file for sublist in [glob(os.path.join(read_dir,file)) for file in filenames] for file in sublist])
        if not files:
            raise FileNotFoundError('No such file: ',filenames)
    elif method=='netcdf':
        if isinstance(filenames,dict): 
            files = {}
            for group in filenames.keys():
                if isinstance(filenames[group],str):
                    files[group] = sorted([file for sublist in [glob(os.path.join(read_dir,file)) for file in [filenames[group]]] for file in sublist])
                else:
                    files[group] = sorted([file for sublist in [glob(os.path.join(read_dir,file)) for file in filenames[group]] for file in sublist])
                if not files[group]:
                    raise FileNotFoundError('No such file: ', filenames[group])
        else:
            raise TypeError('NetCDF format filenames need to be specified as a dict, with format {group1:str or iterable of filenames, group2:...}')
    # Set analysis.read such that it now contains expanded filenames so user has list of read files
    expanded_filenames = getattr(analysis,'read')
    expanded_filenames[attr]['filenames'] = files 
    setattr(analysis, 'read', expanded_filenames)

    # for converting name of attribute to name of class for constructing
    class_names = {'paired':'pair','models':'model','obs':'observation'}

    if method=='pkl':
        if len(files)==1:
            setattr(analysis, attr, read_pkl(files[0]))
        elif len(files)>1:
            for count, file in enumerate(files):
                if count==0:
                    attr_out = read_pkl(file)
                else:
                    attr_append = read_pkl(file)
                    for group in attr_out.keys():
                        attr_out[group].obj = xr.merge([attr_out[group].obj,attr_append[group].obj])
            setattr(analysis, attr,  attr_out)

    elif method=='netcdf':
        xr_dict = {}
        for group in files.keys():
            if isinstance(files[group],str):
                group_files = [files[group]]
            else:
                group_files = files[group]
            xr_dict[group] = read_analysis_ncf(group_files,xr_kws)
        setattr(analysis, attr,  xarray_to_class(class_type=class_names[attr],group_ds=xr_dict))

def read_pkl(filename):
    """Function to read a pickle file containing part of the analysis class (models, obs, paired)

    Parameters
    ----------
    filename : type
        Description of parameter `filename`.
        
    Returns
    -------
    obj : type
        Description of returned object.

    """
    from joblib import load
    
    print('Reading:', filename)
    with open(filename, 'rb') as file:
        obj = load(file)
        
    return obj

def read_analysis_ncf(filenames,xr_kws={}):
    """Function to read netcdf4 files containing an object within an attribute of a part of the
    analysis class (models, obs, paired). For example, a single model/obs pairing or a single model. 
    If the object is saved in multiple files, the function will merge the files.

    Parameters
    ----------
    filenames : str or iterable
        Description of parameter `filename`.
    xr_kws : optional
        Additional keyword arguments for xr.open_dataset()
        
    Returns
    -------
    ds_out : type
        Xarray dataset containing merged files.

    """
    import xarray as xr
    
    if len(filenames)==1:
        print('Reading: ', filenames[0])
        ds_out = xr.open_dataset(filenames[0],**xr_kws)
        
    elif len(filenames)>1:
        for count, file in enumerate(filenames):
            print('Reading: ', file)

            if count==0:
                ds_out = xr.open_dataset(file,**xr_kws)
                group_name1 =  ds_out.attrs['group_name']
                if 'time' not in ds_out.dims:
                    ds_out = ds_out.swap_dims({'x':'time'})
                    print(ds_out)
            else:
                print('appending')
                
                ds_append = xr.open_dataset(file,**xr_kws)
                if 'time' not in ds_append.dims:
                    ds_append = ds_append.swap_dims({'x':'time'})
                # Test if all the files have the same group to prevent merge issues
                if group_name1 != ds_append.attrs['group_name']:
                    raise Exception('The group names are not consistent between the netcdf files being read.') 
                else:
                    print(ds_out.dims,ds_append.dims)
                    ds_out = xr.merge([ds_out,ds_append])
            
    return ds_out

def xarray_to_class(class_type,group_ds):
    """Remake dict containing driver class instances from dict of xarray datasets. Dict of xarray datasets must contain 
    global attribute that contains json formatted class attributes.

    Parameters
    ----------
    class_type : str
        One of 'model', 'pair' or 'observation'
    group_ds : dict
        dict containing xarray datasets from read_grouped_ncf.

    Returns
    -------
    class_dict
    """
    import json
    from melodies_monet import driver
    
    class_dict = {}
    for group in group_ds.keys():
        if class_type == 'pair':
            c=driver.pair()
        elif class_type == 'model':
            c=driver.model()
        elif class_type == 'observation':
            c=driver.observation()

        obj_dict = json.loads(group_ds[group].attrs['dict_json'])
        
        for attr in obj_dict.keys():
            setattr(c, attr, obj_dict[attr])
        c.obj = group_ds[group]
        class_dict[group]=c

    return class_dict
