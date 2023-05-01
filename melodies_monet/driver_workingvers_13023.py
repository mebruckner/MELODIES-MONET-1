""" This is the overall control file.  It will drive the entire analysis package"""
import monetio as mio
import monet as m
import os
import xarray as xr
import pandas as pd
import numpy as np
import datetime

from .util import write_util

__all__ = (
    "pair",
    "observation",
    "model",
    "analysis",
)


class pair:
    """The pair class.

    The pair class pairs model data 
    directly with observational data along time and space.
    """
    
    def __init__(self):
        """Initialize a :class:`pair` object.
    
        Returns
        -------
        pair
        """
        self.type = 'pt_sfc'
        self.radius_of_influence = 1e6
        self.obs = None
        self.model = None
        self.model_vars = None
        self.obs_vars = None
        self.filename = None

    def fix_paired_xarray(self, dset):
        """Reformat the paired dataset.
    
        Parameters
        ----------
        dset : xarray.Dataset
        
        Returns
        -------
        xarray.Dataset
            Reformatted paired dataset.
        """
        # first convert to dataframe
        df = dset.to_dataframe().reset_index(drop=True)

        # now get just the single site index
        dfpsite = df.rename({'siteid': 'x'}, axis=1).drop_duplicates(subset=['x'])
        columns = dfpsite.columns  # all columns
        site_columns = [
            'latitude',
            'longitude',
            'x',
            'site',
            'msa_code',
            'cmsa_name',
            'epa_region',
            'state_name',
            'msa_name',
            'site',
            'utcoffset',
        ]  # only columns for single site identificaiton

        # site only xarray obj (no time dependence)
        dfps = dfpsite.loc[:, columns[columns.isin(site_columns)]].set_index(['x']).to_xarray()  # single column index

        # now pivot df and convert back to xarray using only non site_columns
        site_columns.remove('x')  # need to keep x to merge later
        dfx = df.loc[:, df.columns[~df.columns.isin(site_columns)]].rename({'siteid': 'x'}, axis=1).set_index(['time', 'x']).to_xarray()

        # merge the time dependent and time independent
        out = xr.merge([dfx, dfps])

        # reset x index and add siteid back to the xarray object
        if ~pd.api.types.is_numeric_dtype(out.x):
            siteid = out.x.values
            out['x'] = range(len(siteid))
            out['siteid'] = (('x'), siteid)

        return out


class observation:
    """The observation class.
    
    A class with information and data from an observational dataset.
    """

    def __init__(self):
        """Initialize an :class:`observation` object.

        Returns
        -------
        observation
        """
        self.obs = None
        self.label = None
        self.file = None
        self.obj = None
        self.type = None
        self.debug = None
        self.variable_dict = None

    def open_obs(self):
        """Open the observational data, store data in observation pair,
        and apply mask and scaling.

        Returns
        -------
        None
        """
        from glob import glob
        from numpy import sort
        
        try:
            if os.path.isfile(self.file):
                _, extension = os.path.splitext(self.file)
                if extension in ['.nc', '.ncf', '.netcdf', '.nc4']:
                    if len(glob(self.file)) > 1:
                        self.obj = xr.open_mfdataset(sort(glob(self.file)))
                    self.obj = xr.open_dataset(self.file)
                elif extension in ['.ict', '.icarrt']:
                    self.obj = mio.icarrt.add_data(self.file)
                self.mask_and_scale()  # mask and scale values from the control values
        except ValueError:
            print('something happened opening file')
            
    def open_sat_obs(self):
        """Methods to opens satellite data observations. 
        Uses in-house python code to open and load observations.
        Alternatively may use the satpy reader.

        Returns
        -------
        type
            Fills the object class associated with the equivalent label (self.label) with satellite observation
            dataset read in from the associated file (self.file) by the satellite file reader
        """
        from glob import glob
        
        #import sys
        #sys. exit()  

        try:
            if self.label == 'omps_limb':
                self.obj = mio.omps_limb.read_omps_limb(self.file)
            elif self.label == 'omps_nm':
                self.obj = mio.sat._omps_nadir_mm.read_OMPS_nm(self.file)
            elif self.label == 'mopitt_l3':
                from new_monetio import mopitt_grid
                print('Reading MOPITT')
                self.obj = mopitt_grid.readMOPITTfiles(str(self.file), 'column')
            elif self.label == 'modis_l2':
                from monetio import modis_l2
                print('Reading MODIS L2')
                self.obj = modis_l2.read_mfdataset(
                    self.file, self.variable_dict, debug=self.debug)
            elif self.label == 'tropomi_l2_no2':
                from monetio import tropomi_l2_no2
                print('Reading TROPOMI L2 NO2')
                self.obj = tropomi_l2_no2.read_trpdataset(
                    self.file, self.variable_dict, debug=self.debug)
            else: print('file reader not implemented for {} observation'.format(self.label))
        except ValueError:
            print('something happened opening file')
            
    def mask_and_scale(self):
        """Mask and scale observations, including unit conversions and setting
        detection limits.
        
        Returns
        -------
        None
        """
        vars = self.obj.data_vars
        if self.variable_dict is not None:
            for v in vars:
                if v in self.variable_dict:
                    d = self.variable_dict[v]
                    # Apply removal of min, max, and nan on the units in the obs file first.
                    if 'obs_min' in d:
                        self.obj[v].data = self.obj[v].where(self.obj[v] >= d['obs_min'])
                    if 'obs_max' in d:
                        self.obj[v].data = self.obj[v].where(self.obj[v] <= d['obs_max'])
                    if 'nan_value' in d:
                        self.obj[v].data = self.obj[v].where(self.obj[v] != d['nan_value'])
                    # Then apply a correction if needed for the units.
                    if 'unit_scale' in d:
                        scale = d['unit_scale']
                    else:
                        scale = 1
                    if 'unit_scale_method' in d:
                        if d['unit_scale_method'] == '*':
                            self.obj[v].data *= scale
                        elif d['unit_scale_method'] == '/':
                            self.obj[v].data /= scale
                        elif d['unit_scale_method'] == '+':
                            self.obj[v].data += scale
                        elif d['unit_scale_method'] == '-':
                            self.obj[v].data += -1 * scale

    def obs_to_df(self):
        """Convert and reformat observation object (:attr:`obj`) to dataframe.

        Returns
        -------
        None
        """
        try:
            self.obj = self.obj.to_dataframe().reset_index().drop(['x', 'y'], axis=1)
        except KeyError:
            self.obj = self.obj.to_dataframe().reset_index().drop(['x'], axis=1)

class model:
    """The model class.
    
    A class with information and data from model results.
    """    

    def __init__(self):
        """Initialize a :class:`model` object.

        Returns
        -------
        model
        """
        self.model = None
        self.apply_ak = False
        self.radius_of_influence = None
        self.mod_kwargs = {}
        self.file_str = None
        self.files = None
        self.file_vert_str = None
        self.files_vert = None
        self.file_surf_str = None
        self.files_surf = None
        self.file_pm25_str = None
        self.files_pm25 = None
        self.label = None
        self.obj = None
        self.mapping = None
        self.variable_dict = None
        self.plot_kwargs = None

    def glob_files(self):
        """Convert the model file location string read in by the yaml file
        into a list of files containing all model data.

        Returns
        -------
        None
        """
        from numpy import sort  # TODO: maybe use `sorted` for this
        from glob import glob

        #print(len(self.file_str))
        #if len(self.file_str) == 1:
        self.files = sort(glob(self.file_str))
        
        # add option to read list of files from text file
        if 'txt' in self.file_str:
            with open(self.file_str,'r') as f:
                self.files = f.read().split(' \n')[:-1]
       
        #    self.files = sort(self.file_str)
        if self.file_vert_str is not None:
            self.files_vert = sort(glob(self.file_vert_str))
        if self.file_surf_str is not None:
            self.files_surf = sort(glob(self.file_surf_str))
        if self.file_pm25_str is not None:
            self.files_pm25 = sort(glob(self.file_pm25_str))

    def open_model_files(self):
        """Open the model files, store data in :class:`model` instance attributes,
        and apply mask and scaling.
        
        Models supported are cmaq, wrfchem, rrfs, and gsdchem.
        If a model is not supported, MELODIES-MONET will try to open 
        the model data using a generic reader. If you wish to include new 
        models, add the new model option to this module.

        Returns
        -------
        None
        """
        print(self.model.lower())
        self.glob_files()
        # Calculate species to input into MONET, so works for all mechanisms in wrfchem
        # I want to expand this for the other models too when add aircraft data.
        list_input_var = []
        for obs_map in self.mapping:
            list_input_var = list_input_var + list(set(self.mapping[obs_map].keys()) - set(list_input_var))
        #Only certain models need this option for speeding up i/o.
        if 'cmaq' in self.model.lower():
            self.mod_kwargs.update({'var_list' : list_input_var})
            if self.files_vert is not None:
                self.mod_kwargs.update({'fname_vert' : self.files_vert})
            if self.files_surf is not None:
                self.mod_kwargs.update({'fname_surf' : self.files_surf})
            from .new_monetio import cmaq as cmaq  # Eventually add to monet itself.
            self.obj = cmaq.open_mfdataset(self.files,**self.mod_kwargs)
        elif 'wrfchem' in self.model.lower():
            self.mod_kwargs.update({'var_list' : list_input_var})
            from .new_monetio import wrfchem as wrfchem  # Eventually add to monet itself.
            self.obj = wrfchem.open_mfdataset(self.files,**self.mod_kwargs)
        elif 'rrfs' in self.model.lower():
            if self.files_pm25 is not None:
                self.mod_kwargs.update({'fname_pm25' : self.files_pm25})
            self.mod_kwargs.update({'var_list' : list_input_var})
            from .new_monetio import rrfs_cmaq as rrfs_cmaq  # Eventually add to monet itself.            
            self.obj = rrfs_cmaq.open_mfdataset(self.files,**self.mod_kwargs)
        elif 'gsdchem' in self.model.lower():
            if len(self.files) > 1:
                self.obj = mio.fv3chem.open_mfdataset(self.files,**self.mod_kwargs)
            else:
                self.obj = mio.fv3chem.open_dataset(self.files,**self.mod_kwargs)
        elif 'fv3raqms' in self.model.lower():
        #    print(self.files)
            if len(self.files) > 1:
                self.obj = mio.models.fv3raqms.open_mfdataset(self.files)
            else:
                self.obj = mio.models.fv3raqms.open_dataset(self.files)
            self.obj = self.obj.rename({'sfcp':'surfpres_pa','dpm':'dp_pa','pdash':'pres_pa'})
            self.obj['surfpres_pa'] *= 100
            self.obj['dp_pa'] *= 100
            
        elif 'raqms' in self.model.lower():
            if len(self.files) > 1:
                self.obj = mio.raqms.open_mfdataset(self.files,**self.mod_kwargs)
            else:
                self.obj = mio.raqms.open_dataset(self.files,**self.mod_kwargs)

        else:
            if len(self.files) > 1:
                self.obj = xr.open_mfdataset(self.files,**self.mod_kwargs)
            else:
                self.obj = xr.open_dataset(self.files[0],**self.mod_kwargs)
        self.mask_and_scale()

    def mask_and_scale(self):
        """Mask and scale observations including unit conversions and setting
        detection limits.

        Returns
        -------
        None
        """
        vars = self.obj.data_vars
        if self.variable_dict is not None:
            for v in vars:
                if v in self.variable_dict:
                    d = self.variable_dict[v]
                    if 'unit_scale' in d:
                        scale = d['unit_scale']
                    else:
                        scale = 1
                    if 'unit_scale_method' in d:
                        if d['unit_scale_method'] == '*':
                            self.obj[v].data *= scale
                        elif d['unit_scale_method'] == '/':
                            self.obj[v].data /= scale
                        elif d['unit_scale_method'] == '+':
                            self.obj[v].data += scale
                        elif d['unit_scale_method'] == '-':
                            self.obj[v].data += -1 * scale


class analysis:
    """The analysis class.
    
    The analysis class is the highest
    level class and stores all information about the analysis. It reads 
    and stores information from the input yaml file and defines 
    overarching analysis information like the start and end time, which 
    models and observations to pair, etc.
    """

    def __init__(self):
        """Initialize the :class:`analysis` object.

        Returns
        -------
        analysis
        """
        self.control = 'control.yaml'
        self.control_dict = None
        self.models = {}
        """dict : Models, set by :meth:`open_models`."""
        self.obs = {}
        """dict : Observations, set by :meth:`open_obs`."""
        self.paired = {}
        """dict : Paired data, set by :meth:`pair_data`."""
        self.start_time = None
        self.end_time = None
        self.download_maps = True  # Default to True
        self.output_dir = None
        self.debug = False
        self.save_paired = False
        self.paired_files = {}
    def read_control(self, control=None):
        """Read the input yaml file,
        updating various :class:`analysis` instance attributes.

        Parameters
        ----------
        control : str
            Input yaml file path.
            If provided, :attr:`control` will be set to this value.

        Returns
        -------
        type
            Reads the contents of the yaml control file into a dictionary associated with the analysis class.
        """
        import yaml

        if control is not None:
            self.control = control

        with open(self.control, 'r') as stream:
            self.control_dict = yaml.safe_load(stream)

        # set analysis time
        self.start_time = pd.Timestamp(self.control_dict['analysis']['start_time'])
        self.end_time = pd.Timestamp(self.control_dict['analysis']['end_time'])
        if 'output_dir' in self.control_dict['analysis'].keys():
            self.output_dir = self.control_dict['analysis']['output_dir']
        self.debug = self.control_dict['analysis']['debug']
        self.save_paired = self.control_dict['analysis']['save_paired']
    def open_models(self):
        """Open all models listed in the input yaml file and create a :class:`model` 
        object for each of them, populating the :attr:`models` dict.

        Returns
        -------
        None
        """
        if 'model' in self.control_dict:
            # open each model
            for mod in self.control_dict['model']:
                # create a new model instance
                m = model()
                # this is the model type (ie cmaq, rapchem, gsdchem etc)
                m.model = self.control_dict['model'][mod]['mod_type']
                # set the model label in the dictionary and model class instance
                if "apply_ak" in self.control_dict['model'][mod].keys():
                    m.apply_ak = self.control_dict['model'][mod]['apply_ak']
                else:
                    m.apply_ak = False
                if 'radius_of_influence' in self.control_dict['model'][mod].keys():
                    m.radius_of_influence = self.control_dict['model'][mod]['radius_of_influence']
                else:
                    m.radius_of_influence = 1e6
                if 'initial_file' in self.control_dict['model'][mod].keys(): 
                    m.initial_file = self.control_dict['model'][mod]['initial_file']
                else: m.initial_file = False
                if 'last_file' in self.control_dict['model'][mod].keys(): 
                    m.last_file = self.control_dict['model'][mod]['last_file']
                else: m.last_file = False
                        
                if 'mod_kwargs' in self.control_dict['model'][mod].keys():
                    m.mod_kwargs = self.control_dict['model'][mod]['mod_kwargs']    
                m.label = mod
                # create file string (note this can include hot strings)
                m.file_str = self.control_dict['model'][mod]['files']
                if 'files_vert' in self.control_dict['model'][mod].keys():
                    m.file_vert_str = self.control_dict['model'][mod]['files_vert']
                if 'files_surf' in self.control_dict['model'][mod].keys():
                    m.file_surf_str = self.control_dict['model'][mod]['files_surf']
                if 'files_pm25' in self.control_dict['model'][mod].keys():
                    m.file_pm25_str = self.control_dict['model'][mod]['files_pm25']
                # create mapping
                m.mapping = self.control_dict['model'][mod]['mapping']
                # add variable dict
                print(mod)
                print(self.control_dict['model'][mod])
                if 'variables' in self.control_dict['model'][mod].keys():
                    m.variable_dict = self.control_dict['model'][mod]['variables']
                if 'plot_kwargs' in self.control_dict['model'][mod].keys():
                    m.plot_kwargs = self.control_dict['model'][mod]['plot_kwargs']
                # open the model
                m.open_model_files()
                self.models[m.label] = m

    def open_obs(self):
        """Open all observations listed in the input yaml file and create an 
        :class:`observation` instance for each of them,
        populating the :attr:`obs` dict.

        Returns
        -------
        None
        """
        if 'obs' in self.control_dict:
            for obs in self.control_dict['obs']:
                o = observation()
                o.obs = obs
                o.label = obs
                o.obs_type = self.control_dict['obs'][obs]['obs_type']
                o.file = self.control_dict['obs'][obs]['filename']
                if 'debug' in self.control_dict['obs'][obs].keys():
                    o.debug = self.control_dict['obs'][obs]['debug']
                if 'variables' in self.control_dict['obs'][obs].keys():
                    o.variable_dict = self.control_dict['obs'][obs]['variables']
                if o.obs_type == 'pt_sfc':    
                    o.open_obs()
                elif o.obs_type in ['sat_swath_sfc', 'sat_swath_clm', 'sat_grid_sfc',\
                                    'sat_grid_clm', 'sat_swath_prof']:
                    o.open_sat_obs()
                self.obs[o.label] = o


    def pair_data(self):
        """Pair all observations and models in the analysis class
        (i.e., those listed in the input yaml file) together,
        populating the :attr:`paired` dict.

        Returns
        -------
        None
        """
        pairs = {}  # TODO: unused
        for model_label in self.models:
            mod = self.models[model_label]
            # Now we have the models we need to loop through the mapping table for each network and pair the data
            # each paired dataset will be output to a netcdf file with 'model_label_network.nc'
            for obs_to_pair in mod.mapping.keys():
                # get the variables to pair from the model data (ie don't pair all data)
                keys = [key for key in mod.mapping[obs_to_pair].keys()]
                obs_vars = [mod.mapping[obs_to_pair][key] for key in keys]

                model_obj = mod.obj[keys]
                ## TODO:  add in ability for simple addition of variables from

                # simplify the objs object with the correct mapping vairables
                obs = self.obs[obs_to_pair]

                # pair the data
                # if pt_sfc (surface point network or monitor)
                if obs.obs_type.lower() == 'pt_sfc':
                    # convert this to pandas dataframe unless already done because second time paired this obs
                    if not isinstance(obs.obj, pd.DataFrame):
                        obs.obs_to_df()
                    #Check if z dim is larger than 1. If so select, the first level as all models read through 
                    #MONETIO will be reordered such that the first level is the level nearest to the surface.
                    # MEB: altered to include try/except logic to take care of case when there is no z dimension to deal with.
                    #      this was necessary for aeronet/raqms case.
                    try:
                         if model_obj.sizes['z'] > 1: 
                            model_obj = model_obj.isel(z=0).expand_dims('z',axis=1) #Select only the surface values to pair with obs.
                    except KeyError:
                        pass
                    # now combine obs with
                    paired_data = model_obj.monet.combine_point(obs.obj, radius_of_influence=mod.radius_of_influence, suffix=mod.label)
                    # print(paired_data)
                    # this outputs as a pandas dataframe.  Convert this to xarray obj
                    p = pair()
                    p.obs = obs.label
                    p.model = mod.label
                    p.model_vars = keys
                    p.obs_vars = obs_vars
                    p.filename = '{}_{}.nc'.format(p.obs, p.model)
                    p.obj = paired_data.monet._df_to_da()
                    label = "{}_{}".format(p.obs, p.model)
                    self.paired[label] = p
                    p.obj = p.fix_paired_xarray(dset=p.obj)
                    # write_util.write_ncf(p.obj,p.filename) # write out to file
                # TODO: add other network types / data types where (ie flight, satellite etc)
                elif obs.obs_type.lower() == 'sat_swath_clm':
                    
                    if obs.label == 'omps_nm':
                        print(model_obj)
                        has_1st = mod.initial_file
                        has_nth = mod.last_file
                        from .util import satellite_utilities as sutil
                        if mod.apply_ak == True:
                            keys.append('pres_pa_mid')
                            keys.append('surfpres_pa')
                            model_obj = mod.obj[keys]
                            paired_data = sutil.omps_nm_pairing_apriori(model_obj,obs.obj,has_1st,has_nth)
                        else:
                            keys.append('dp_pa')
                            model_obj = mod.obj[keys]
                            paired_data = sutil.omps_nm_pairing(model_obj,obs.obj,keys,has_1st,has_nth)
                        #paired_data['o3vmr'][(paired_data['o3vmr'] < 150)] = np.nan
                        paired_data = paired_data.where(paired_data.o3vmr > 0)
                        p = pair()
                        p.obs = obs.label
                        p.model = mod.label
                        p.model_vars = keys
                        p.obs_vars = obs_vars
                        p.obj = paired_data 
                        label = '{}_{}'.format(p.obs,p.model)
                        self.paired[label] = p
                if self.save_paired:
                    otime1 = obs.obj.time[0].dt.strftime('%Y%m%d%H').values
                    otime2 = obs.obj.time[-1].dt.strftime('%Y%m%d%H').values
                    paired_fname = '{}_{}_{}.nc'.format(label,otime1,otime2)
                    write_util.write_ncf(p.obj,paired_fname)
                    if label not in self.paired_files.keys():
                        self.paired_files[label] = []
                    self.paired_files[label].append(paired_fname)
    ### TODO: Create the plotting driver (most complicated one)
    # def plotting(self):
    def plotting(self):
        """Cycle through all the plotting groups (e.g., plot_grp1) listed in 
        the input yaml file and create the plots.
        
        This routine loops over all the domains and
        model/obs pairs specified in the plotting group (``.control_dict['plots']``)
        for all the variables specified in the mapping dictionary listed in 
        :attr:`paired`.

        Creates plots stored in the file location specified by output_dir
        in the analysis section of the yaml file.

        Returns
        -------
        None
        """
	
        obs_to_pair = list(self.models[(list(self.models.keys()))[0]].mapping.keys())[0]
        if self.obs[obs_to_pair].obs_type.lower() == 'pt_sfc': 
            from .plots import surfplots as splots
        else:
            from .plots import satplots as splots
        from .new_monetio import code_to_move_to_monet as code_m_new

        # first get the plotting dictionary from the yaml file
        plot_dict = self.control_dict['plots']
        # Calculate any items that do not need to recalculate each loop.
        startdatename = str(datetime.datetime.strftime(self.start_time, '%Y-%m-%d_%H'))
        enddatename = str(datetime.datetime.strftime(self.end_time, '%Y-%m-%d_%H'))
        # now we are going to loop through each plot_group (note we can have multiple plot groups)
        # a plot group can have
        #     1) a singular plot type
        #     2) multiple paired datasets or model datasets depending on the plot type
        #     3) kwargs for creating the figure ie size and marker (note the default for obs is 'x')
        for grp, grp_dict in plot_dict.items():
            pair_labels = grp_dict['data']
            # get the plot type
            plot_type = grp_dict['type']

            # first get the observational obs labels
            pair1 = self.paired[list(self.paired.keys())[0]]
            obs_vars = pair1.obs_vars

            # loop through obs variables
            for obsvar in obs_vars:
                # Loop also over the domain types. So can easily create several overview and zoomed in plots.
                domain_types = grp_dict['domain_type']
                domain_names = grp_dict['domain_name']
                for domain in range(len(domain_types)):
                    domain_type = domain_types[domain]
                    domain_name = domain_names[domain]

                    # Then loop through each of the pairs to add to the plot.
                    for p_index, p_label in enumerate(pair_labels):
                        p = self.paired[p_label]
                        # find the pair model label that matches the obs var
                        index = p.obs_vars.index(obsvar)
                        modvar = p.model_vars[index]

                        # Adjust the modvar as done in pairing script, if the species name in obs and model are the same.
                        if obsvar == modvar:
                            modvar = modvar + '_new'
                            
                        if self.obs[obs_to_pair].obs_type.lower() == 'pt_sfc':
                            # convert to dataframe and ensure index is time
                            pairdf_all = p.obj.to_dataframe().reset_index().set_index('time')

                            # Select only the analysis time window.
                            pairdf_all = pairdf_all.loc[self.start_time : self.end_time]
                        else:
                            # convert index to time
                            pairdf_all = p.obj.swap_dims({'x':'time'})

                            # Select only the analysis time window.
                            pairdf_all = pairdf_all.sel(time=slice(self.start_time,self.end_time))
                            print(pairdf_all)
                        # Determine the default plotting colors.
                        if 'default_plot_kwargs' in grp_dict.keys():
                            if self.models[p.model].plot_kwargs is not None:
                                plot_dict = {**grp_dict['default_plot_kwargs'], **self.models[p.model].plot_kwargs}
                            else:
                                plot_dict = {**grp_dict['default_plot_kwargs'], **splots.calc_default_colors(p_index)}
                            obs_dict = grp_dict['default_plot_kwargs']
                        else:
                            if self.models[p.model].plot_kwargs is not None:
                                plot_dict = self.models[p.model].plot_kwargs
                            else:
                                plot_dict = splots.calc_default_colors(p_index)
                            obs_dict = None

                        # Determine figure_kwargs and text_kwargs
                        if 'fig_kwargs' in grp_dict.keys():
                            fig_dict = grp_dict['fig_kwargs']
                        else:
                            fig_dict = None
                        if 'text_kwargs' in grp_dict.keys():
                            text_dict = grp_dict['text_kwargs']
                        else:
                            text_dict = None

                        # Read in some plotting specifications stored with observations.
                        if self.obs[p.obs].variable_dict is not None:
                            if obsvar in self.obs[p.obs].variable_dict.keys():
                                obs_plot_dict = self.obs[p.obs].variable_dict[obsvar]
                            else:
                                obs_plot_dict = {}
                        else:
                            obs_plot_dict = {}

                        # Specify ylabel if noted in yaml file.
                        if 'ylabel_plot' in obs_plot_dict.keys():
                            use_ylabel = obs_plot_dict['ylabel_plot']
                        else:
                            use_ylabel = None

                        # Determine if set axis values or use defaults
                        if grp_dict['data_proc']['set_axis'] == True:
                            if obs_plot_dict:  # Is not null
                                set_yaxis = True
                            else:
                                print('Warning: variables dict for ' + obsvar + ' not provided, so defaults used')
                                set_yaxis = False
                        else:
                            set_yaxis = False

                        # Determine outname
                        outname = "{}.{}.{}.{}.{}.{}.{}".format(grp, plot_type, obsvar, startdatename, enddatename, domain_type, domain_name)
                        if self.output_dir is not None:
                            outname = self.output_dir + '/' + outname  # Extra / just in case.

                        # Query selected points if applicable
                        if domain_type != 'all':
                            pairdf_all.query(domain_type + ' == ' + '"' + domain_name + '"', inplace=True)

                        # Drop NaNs if using pandas 
                        if self.obs[obs_to_pair].obs_type.lower() == 'pt_sfc':
                            if grp_dict['data_proc']['rem_obs_nan'] == True:
                                # I removed drop=True in reset_index in order to keep 'time' as a column.
                                pairdf = pairdf_all.reset_index().dropna(subset=[modvar, obsvar])
                            else:
                                pairdf = pairdf_all.reset_index().dropna(subset=[modvar])
                        else:
                            pairdf = pairdf_all
                        # Types of plots
                        if plot_type.lower() == 'timeseries':
                            if set_yaxis == True:
                                if all(k in obs_plot_dict for k in ('vmin_plot', 'vmax_plot')):
                                    vmin = obs_plot_dict['vmin_plot']
                                    vmax = obs_plot_dict['vmax_plot']
                                else:
                                    print('Warning: vmin_plot and vmax_plot not specified for ' + obsvar + ', so default used.')
                                    vmin = None
                                    vmax = None
                            else:
                                vmin = None
                                vmax = None
                            # Select time to use as index.
                            if self.obs[obs_to_pair].obs_type.lower() == 'pt_sfc': 
                                pairdf = pairdf.set_index(grp_dict['data_proc']['ts_select_time'])
                            a_w = grp_dict['data_proc']['ts_avg_window']
                            if p_index == 0:
                                # First plot the observations.
                                ax = splots.make_timeseries(
                                    pairdf,
                                    column=obsvar,
                                    label=p.obs,
                                    avg_window=a_w,
                                    ylabel=use_ylabel,
                                    vmin=vmin,
                                    vmax=vmax,
                                    domain_type=domain_type,
                                    domain_name=domain_name,
                                    plot_dict=obs_dict,
                                    fig_dict=fig_dict,
                                    text_dict=text_dict,
                                    debug=self.debug
                                )
                            # For all p_index plot the model.
                            ax = splots.make_timeseries(
                                pairdf,
                                column=modvar,
                                label=p.model,
                                ax=ax,
                                avg_window=a_w,
                                ylabel=use_ylabel,
                                vmin=vmin,
                                vmax=vmax,
                                domain_type=domain_type,
                                domain_name=domain_name,
                                plot_dict=plot_dict,
                                text_dict=text_dict,
                                debug=self.debug
                            )
                            # At the end save the plot.
                            if p_index == len(pair_labels) - 1:
                                code_m_new.savefig(outname + '.png', loc=2, height=150, decorate=True, bbox_inches='tight', dpi=200)
                        if plot_type.lower() == 'boxplot':
                            if set_yaxis == True:
                                if all(k in obs_plot_dict for k in ('vmin_plot', 'vmax_plot')):
                                    vmin = obs_plot_dict['vmin_plot']
                                    vmax = obs_plot_dict['vmax_plot']
                                else:
                                    print('Warning: vmin_plot and vmax_plot not specified for ' + obsvar + ', so default used.')
                                    vmin = None
                                    vmax = None
                            else:
                                vmin = None
                                vmax = None
                            # First for p_index = 0 create the obs box plot data array.
                            if p_index == 0:
                                comb_bx, label_bx = splots.calculate_boxplot(pairdf, column=obsvar, label=p.obs, plot_dict=obs_dict)
                            # Then add the models to this dataarray.
                            comb_bx, label_bx = splots.calculate_boxplot(
                                pairdf, column=modvar, label=p.model, plot_dict=plot_dict, comb_bx=comb_bx, label_bx=label_bx
                            )
                            # For the last p_index make the plot.
                            if p_index == len(pair_labels) - 1:
                                splots.make_boxplot(
                                    comb_bx,
                                    label_bx,
                                    ylabel=use_ylabel,
                                    vmin=vmin,
                                    vmax=vmax,
                                    outname=outname,
                                    domain_type=domain_type,
                                    domain_name=domain_name,
                                    plot_dict=obs_dict,
                                    fig_dict=fig_dict,
                                    text_dict=text_dict,
                                    debug=self.debug
                                )
                        elif plot_type.lower() == 'taylor':
                            if set_yaxis == True:
                                if 'ty_scale' in obs_plot_dict.keys():
                                    ty_scale = obs_plot_dict['ty_scale']
                                else:
                                    print('Warning: ty_scale not specified for ' + obsvar + ', so default used.')
                                    ty_scale = 1.5  # Use default
                            else:
                                ty_scale = 1.5  # Use default
                            if p_index == 0:
                                # Plot initial obs/model
                                dia = splots.make_taylor(
                                    pairdf,
                                    column_o=obsvar,
                                    label_o=p.obs,
                                    column_m=modvar,
                                    label_m=p.model,
                                    ylabel=use_ylabel,
                                    ty_scale=ty_scale,
                                    domain_type=domain_type,
                                    domain_name=domain_name,
                                    plot_dict=plot_dict,
                                    fig_dict=fig_dict,
                                    text_dict=text_dict,
                                    debug=self.debug
                                )
                            else:
                                # For the rest, plot on top of dia
                                dia = splots.make_taylor(
                                    pairdf,
                                    column_o=obsvar,
                                    label_o=p.obs,
                                    column_m=modvar,
                                    label_m=p.model,
                                    dia=dia,
                                    ylabel=use_ylabel,
                                    ty_scale=ty_scale,
                                    domain_type=domain_type,
                                    domain_name=domain_name,
                                    plot_dict=plot_dict,
                                    text_dict=text_dict,
                                    debug=self.debug
                                )
                            # At the end save the plot.
                            if p_index == len(pair_labels) - 1:
                                code_m_new.savefig(outname + '.png', loc=2, height=70, decorate=True, bbox_inches='tight', dpi=200)
                        elif plot_type.lower() == 'spatial_bias':
                            if set_yaxis == True:
                                if 'vdiff_plot' in obs_plot_dict.keys():
                                    vdiff = obs_plot_dict['vdiff_plot']
                                else:
                                    print('Warning: vdiff_plot not specified for ' + obsvar + ', so default used.')
                                    vdiff = None
                            else:
                                vdiff = None
                            # p_label needs to be added to the outname for this plot
                            outname = "{}.{}".format(outname, p_label)
                            splots.make_spatial_bias(
                                pairdf,
                                column_o=obsvar,
                                label_o=p.obs,
                                column_m=modvar,
                                label_m=p.model,
                                ylabel=use_ylabel,
                                vdiff=vdiff,
                                outname=outname,
                                domain_type=domain_type,
                                domain_name=domain_name,
                                fig_dict=fig_dict,
                                text_dict=text_dict,
                                debug=self.debug
                            )
                        elif plot_type.lower() == 'gridded_spatial_bias':
                            splots.make_spatial_bias_gridded(
                                pairdf,
                                column_o=obsvar,
                                label_o=p.obs,
                                column_m=modvar,
                                label_m=p.model,
                                ylabel=use_ylabel,
                                #vdiff=vdiff,
                                outname=outname,
                                domain_type=domain_type,
                                domain_name=domain_name,
                                fig_dict=fig_dict,
                                text_dict=text_dict,
                                debug=self.debug
                                )    
                        elif plot_type.lower() == 'spatial_overlay':
                            if set_yaxis == True:
                                if all(k in obs_plot_dict for k in ('vmin_plot', 'vmax_plot', 'nlevels_plot')):
                                    vmin = obs_plot_dict['vmin_plot']
                                    vmax = obs_plot_dict['vmax_plot']
                                    nlevels = obs_plot_dict['nlevels_plot']
                                elif all(k in obs_plot_dict for k in ('vmin_plot', 'vmax_plot')):
                                    vmin = obs_plot_dict['vmin_plot']
                                    vmax = obs_plot_dict['vmax_plot']
                                    nlevels = None
                                else:
                                    print('Warning: vmin_plot and vmax_plot not specified for ' + obsvar + ', so default used.')
                                    vmin = None
                                    vmax = None
                                    nlevels = None
                            else:
                                vmin = None
                                vmax = None
                                nlevels = None
                            #Check if z dim is larger than 1. If so select, the first level as all models read through 
                            #MONETIO will be reordered such that the first level is the level nearest to the surface.
                            # Create model slice and select time window for spatial plots
                            if self.models[p.model].obj.sizes['z'] > 1: #Select only surface values.
                                vmodel = self.models[p.model].obj.isel(z=0).expand_dims('z',axis=1).loc[
                                    dict(time=slice(self.start_time, self.end_time))] 
                            else:
                                vmodel = self.models[p.model].obj.loc[dict(time=slice(self.start_time, self.end_time))]
                            # Determine proj to use for spatial plots
                            proj = splots.map_projection(self.models[p.model])
                            # p_label needs to be added to the outname for this plot
                            outname = "{}.{}".format(outname, p_label)
                            # For just the spatial overlay plot, you do not use the model data from the pair file
                            # So get the variable name again since pairing one could be _new.
                            splots.make_spatial_overlay(
                                pairdf,
                                vmodel,
                                column_o=obsvar,
                                label_o=p.obs,
                                column_m=p.model_vars[index],
                                label_m=p.model,
                                ylabel=use_ylabel,
                                vmin=vmin,
                                vmax=vmax,
                                nlevels=nlevels,
                                proj=proj,
                                outname=outname,
                                domain_type=domain_type,
                                domain_name=domain_name,
                                fig_dict=fig_dict,
                                text_dict=text_dict,
                                debug=self.debug
                            )

    def stats(self):
        """Calculate statistics specified in the input yaml file.
        
        This routine  loops over all the domains and model/obs pairs for all the variables 
        specified in the mapping dictionary listed in :attr:`paired`.
        
        Creates a csv file storing the statistics and optionally a figure 
        visualizing the table.

        Returns
        -------
        None
        """
        from .stats import proc_stats as proc_stats

        # first get the stats dictionary from the yaml file
        stat_dict = self.control_dict['stats']
        # Calculate general items
        startdatename = str(datetime.datetime.strftime(self.start_time, '%Y-%m-%d_%H'))
        enddatename = str(datetime.datetime.strftime(self.end_time, '%Y-%m-%d_%H'))
        stat_list = stat_dict['stat_list']
        # Determine stat_grp full name
        stat_fullname_ns = proc_stats.produce_stat_dict(stat_list=stat_list, spaces=False)
        stat_fullname_s = proc_stats.produce_stat_dict(stat_list=stat_list, spaces=True)
        pair_labels = stat_dict['data']

        # Determine rounding
        if 'round_output' in stat_dict.keys():
            round_output = stat_dict['round_output']
        else:
            round_output = 3

        # Then loop over all the observations
        # first get the observational obs labels
        pair1 = self.paired[list(self.paired.keys())[0]]
        obs_vars = pair1.obs_vars
        for obsvar in obs_vars:
            # Read in some plotting specifications stored with observations.
            if self.obs[pair1.obs].variable_dict is not None:
                if obsvar in self.obs[pair1.obs].variable_dict.keys():
                    obs_plot_dict = self.obs[pair1.obs].variable_dict[obsvar]
                else:
                    obs_plot_dict = {}
            else:
                obs_plot_dict = {}

            # Next loop over all of the domains.
            # Loop also over the domain types.
            domain_types = stat_dict['domain_type']
            domain_names = stat_dict['domain_name']
            for domain in range(len(domain_types)):
                domain_type = domain_types[domain]
                domain_name = domain_names[domain]

                # The tables and text files will be output at this step in loop.
                # Create an empty pandas dataarray.
                df_o_d = pd.DataFrame()
                # Determine outname
                outname = "{}.{}.{}.{}.{}.{}".format('stats', obsvar, domain_type, domain_name, startdatename, enddatename)
                if self.output_dir is not None:
                    outname = self.output_dir + '/' + outname  # Extra / just in case.

                # Determine plotting kwargs
                if 'output_table_kwargs' in stat_dict.keys():
                    out_table_kwargs = stat_dict['output_table_kwargs']
                else:
                    out_table_kwargs = None

                # Add Stat ID and FullName to pandas dictionary.
                df_o_d['Stat_ID'] = stat_list
                df_o_d['Stat_FullName'] = stat_fullname_ns

                # Finally Loop through each of the pairs
                for p_label in pair_labels:
                    p = self.paired[p_label]
                    # Create an empty list to store the stat_var
                    p_stat_list = []

                    # Specify title for stat plots.
                    if 'ylabel_plot' in obs_plot_dict.keys():
                        title = obs_plot_dict['ylabel_plot'] + ': ' + domain_type + ' ' + domain_name
                    else:
                        title = obsvar + ': ' + domain_type + ' ' + domain_name

                    # Loop through each of the stats
                    for stat_grp in stat_list:

                        # find the pair model label that matches the obs var
                        index = p.obs_vars.index(obsvar)
                        modvar = p.model_vars[index]

                        # Adjust the modvar as done in pairing script, if the species name in obs and model are the same.
                        if obsvar == modvar:
                            modvar = modvar + '_new'

                        # convert to dataframe
                        pairdf_all = p.obj.to_dataframe()

                        # Select only the analysis time window.
                        pairdf_all = pairdf_all.loc[self.start_time : self.end_time]

                        # Query selected points if applicable
                        if domain_type != 'all':
                            pairdf_all.query(domain_type + ' == ' + '"' + domain_name + '"', inplace=True)

                        # Drop NaNs for model and observations in all cases.
                        pairdf = pairdf_all.reset_index().dropna(subset=[modvar, obsvar])

                        # Create empty list for all dom
                        # Calculate statistic and append to list
                        if obsvar == 'WD':  # Use separate calculations for WD
                            p_stat_list.append(proc_stats.calc(pairdf, stat=stat_grp, obsvar=obsvar, modvar=modvar, wind=True))
                        else:
                            p_stat_list.append(proc_stats.calc(pairdf, stat=stat_grp, obsvar=obsvar, modvar=modvar, wind=False))

                    # Save the stat to a dataarray
                    df_o_d[p_label] = p_stat_list

                # Save the pandas dataframe to a txt file
                # Save rounded output
                df_o_d = df_o_d.round(round_output)
                df_o_d.to_csv(path_or_buf=outname + '.csv', index=False)

                if stat_dict['output_table'] == True:
                    # Output as a table graphic too.
                    # Change to use the name with full spaces.
                    df_o_d['Stat_FullName'] = stat_fullname_s

                    proc_stats.create_table(df_o_d.drop(columns=['Stat_ID']), 
                                            outname=outname, 
                                            title=title, 
                                            out_table_kwargs=out_table_kwargs,
                                            debug=self.debug
                                           )
