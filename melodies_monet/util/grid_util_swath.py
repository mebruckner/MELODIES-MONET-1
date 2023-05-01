# Copyright (C) 2022 National Center for Atmospheric Research and National Oceanic and Atmospheric Administration
# SPDX-License-Identifier: Apache-2.0
#

#MEB: updating for data that is 2d arrays not 1d arrays,
#     has 1d time, 2d lats/lons

"""
file: grid_util.py
"""

import math
import numpy as np


def update_sparse_data_grid(time_edges, x_edges, y_edges,
                            time_obs, x_obs, y_obs, data_obs,
                            count_grid, data_grid):
    """
    Accumulate obs data on a uniform grid with dimensions (time, x, y)
    Store running counts and sums in dictionaries keyed by grid index tuples (i_time, i_x, i_y)

    Parameters
        time_edges (np.array): grid time edges
        x_edges (np.array): grid x coord edges
        y_edges (np.array): grid y coord edges
        time_obs (np.array): obs times
        x_obs (np.array): obs x coords
        y_obs (np.array): obs y coords
        data_obs (np.array): obs data values
        count_grid (dict): number of obs points in grid cell
        data_grid (dict): sum of data values in grid cell

    Returns
        None
    """
    odim1,odim2 = data_obs.shape
    
    time_del = time_edges[1] - time_edges[0]
    x_del = x_edges[1] - x_edges[0]
    y_del = y_edges[1] - y_edges[0]
    ntime, nx, ny = len(time_edges) - 1, len(x_edges) - 1, len(y_edges) - 1
    for i in range(odim1):
        # check that row contains data
        if not data_obs[i].isnull().all():
            i_time = math.floor((time_obs[i] - time_edges[0]) / time_del)
            for j in range(odim2):
                # check that point contains data
                if not np.isnan(data_obs[i,j]):
                    i_x = math.floor((x_obs[i,j] - x_edges[0]) / x_del)
                    i_y = math.floor((y_obs[i,j] - y_edges[0]) / y_del)
                    i_time = np.clip(i_time, 0, ntime - 1)
                    i_x = np.clip(i_x, 0, nx - 1)
                    i_y = np.clip(i_y, 0, ny - 1)
                    if (i_time, i_x, i_y) in count_grid.keys():
                        count_grid[(i_time, i_x, i_y)] += 1
                        data_grid[(i_time, i_x, i_y)] += data_obs[i,j].values
                    else:
                        count_grid[(i_time, i_x, i_y)] = 1
                        data_grid[(i_time, i_x, i_y)] = data_obs[i,j].values


def normalize_sparse_data_grid(count_grid, data_grid):
    """
    Normalize accumuxed data on a uniform grid

    Parameters
        count_grid (dict): number of obs points in grid cell
        data_grid (dict): sum of data values in grid cell

    Returns
        None
    """
    for index_tuple in count_grid.keys():
        data_grid[index_tuple] /= count_grid[index_tuple]


def sparse_data_to_array(time_edges, x_edges, y_edges,
                         count_grid, data_grid,
                         count_type=np.uint32, data_type=np.float32):
    """
    Convert sparse grid data to numpy arrays

    Parameters
        time_edges (np.array): grid time edges
        x_edges (np.array): grid x coord edges
        y_edges (np.array): grid y coord edges
        count_grid (dict): number of obs points in grid cell
        data_grid (dict): sum of data values in grid cell
        count_type (dtype, default=np.uint32): data type of count_grid_array
        data_type (dtype, default=np.float32): data type of data_grid_array

    Returns
        count_grid_array (np.array): number of obs points in grid cell
        data_grid_array (np.array): sum of data values in grid cell
    """
    ntime, nx, ny = len(time_edges) - 1, len(x_edges) - 1, len(y_edges) - 1
    count_grid_array = np.zeros((ntime, nx, ny), dtype=count_type)
    data_grid_array = np.full((ntime, nx, ny), np.nan, dtype=data_type)
    for index_tuple in count_grid.keys():
        count_grid_array[index_tuple[0], index_tuple[1], index_tuple[2]] = count_grid[index_tuple]
        data_grid_array[index_tuple[0], index_tuple[1], index_tuple[2]] = data_grid[index_tuple]

    return count_grid_array, data_grid_array


def update_data_grid(time_edges, x_edges, y_edges,
                     time_obs, x_obs, y_obs, data_obs,
                     count_grid, data_grid):
    """
    Accumulate obs data on a uniform grid with dimensions (time, x, y)
    Store running counts and sums in numpy arrays

    Parameters
        time_edges (np.array): grid time edges
        x_edges (np.array): grid x coord edges
        y_edges (np.array): grid y coord edges
        time_obs (np.array): obs times
        x_obs (np.array): obs x coords
        y_obs (np.array): obs y coords
        data_obs (np.array): obs data values
        count_grid (np.array): number of obs points in grid cell
        data_grid (np.array): sum of data values in grid cell

    Returns
        None
    """
    odim1,odim2 = data_obs.shape
    time_del = time_edges[1] - time_edges[0]
    x_del = x_edges[1] - x_edges[0]
    y_del = y_edges[1] - y_edges[0]
    ntime, nx, ny = data_grid.shape
    
    for i in range(odim1):
        # check that row contains data
        if not data_obs[i].isnull().all():
            i_time = math.floor((time_obs[i] - time_edges[0]) / time_del)
            for j in range(odim2):
                # check that point contains data
                if not np.isnan(data_obs[i,j]):
                    i_x = math.floor((x_obs[i,j] - x_edges[0]) / x_del)
                    i_y = math.floor((y_obs[i,j] - y_edges[0]) / y_del)
                    i_time = np.clip(i_time, 0, ntime - 1)
                    i_x = np.clip(i_x, 0, nx - 1)
                    i_y = np.clip(i_y, 0, ny - 1)
                    
                    count_grid[(i_time, i_x, i_y)] += 1
                    data_grid[(i_time, i_x, i_y)] += data_obs[i,j].values
    


def normalize_data_grid(count_grid, data_grid):
    """
    Normalize accumuxed data on a uniform grid

    Parameters
        count_grid (np.array): number of obs points in grid cell
        data_grid (np.array): sum of data values in grid cell

    Returns
        None
    """
    data_grid[count_grid == 0] = np.nan
    data_grid[count_grid > 0] /= count_grid[count_grid > 0]

