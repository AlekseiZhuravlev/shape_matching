import torch
import numpy as np

import os
import sys
curr_dir = os.getcwd()
if 's94zalek_hpc' in curr_dir:
    user_name = 's94zalek_hpc'
else:
    user_name = 's94zalek'
sys.path.append(f'/home/{user_name}/shape_matching')

import my_code.datasets.shape_dataset as shape_dataset
import my_code.datasets.template_dataset as template_dataset


def get_val_dataset(name, phase, num_evecs, canonicalize_fmap):
    
    if name == 'SURREAL':
        dataset_single = shape_dataset.SingleShapeDataset(
            data_root = 'data_with_smpl_corr/SURREAL_test',
            centering = 'bbox',
            num_evecs=num_evecs,
            lb_cache_dir=f'data_with_smpl_corr/SURREAL_test/diffusion',
        )   
        dataset_template = template_dataset.TemplateDataset(
            base_dataset=dataset_single,
            template_path='data/SURREAL_full/template/template.ply',
            template_corr=list(range(6890)),
            num_evecs=dataset_single.num_evecs,
            preload_base_dataset=True,
            canonicalize_fmap=canonicalize_fmap,
        )
    elif name == 'FAUST_orig':
        dataset_single = shape_dataset.SingleFaustDataset(
            phase=phase,
            data_root = 'data_with_smpl_corr/FAUST_original',
            centering = 'bbox',
            num_evecs=num_evecs,
            lb_cache_dir=f'data_with_smpl_corr/FAUST_original/diffusion'
        )
        dataset_template = template_dataset.TemplateDataset(
            base_dataset=dataset_single,
            template_path='data/SURREAL_full/template/template.ply',
            template_corr=list(range(6890)),
            num_evecs=dataset_single.num_evecs,
            preload_base_dataset=True,
            canonicalize_fmap=canonicalize_fmap,
        )
    elif name == 'FAUST_r':
        dataset_single = shape_dataset.SingleFaustDataset(
            phase=phase,
            data_root = 'data_with_smpl_corr/FAUST_r',
            centering = 'bbox',
            num_evecs=num_evecs,
            lb_cache_dir=f'data_with_smpl_corr/FAUST_r/diffusion'
        )
        dataset_template = template_dataset.TemplateDataset(
            base_dataset=dataset_single,
            template_path='data/SURREAL_full/template/template.ply',
            template_corr=np.loadtxt('data_with_smpl_corr/FAUST_r/sampleID.vts', dtype=int) - 1,
            num_evecs=dataset_single.num_evecs,
            preload_base_dataset=True,
            canonicalize_fmap=canonicalize_fmap,
        )
    elif name == 'FAUST_a':
        dataset_single = shape_dataset.SingleShapeDataset(
            data_root = 'data_with_smpl_corr/FAUST_a',
            centering = 'bbox',
            num_evecs=num_evecs,
            lb_cache_dir=f'data_with_smpl_corr/FAUST_a/diffusion'
        )
        dataset_template = template_dataset.TemplateDataset(
            base_dataset=dataset_single,
            template_path='data/SURREAL_full/template/template.ply',
            template_corr=list(range(6890)),
            num_evecs=dataset_single.num_evecs,
            preload_base_dataset=True,
            canonicalize_fmap=canonicalize_fmap,
        )
    elif name == 'SHREC19':
        dataset_single = shape_dataset.SingleShapeDataset(
            data_root = 'data_with_smpl_corr/SHREC19_original',
            centering = 'bbox',
            num_evecs=num_evecs,
            lb_cache_dir=f'data_with_smpl_corr/SHREC19_original/diffusion'
        )
        dataset_template = template_dataset.TemplateDataset(
            base_dataset=dataset_single,
            template_path='data/SURREAL_full/template/template.ply',
            template_corr=list(range(6890)),
            num_evecs=dataset_single.num_evecs,
            preload_base_dataset=False,
            canonicalize_fmap=canonicalize_fmap,
        )
        
    return dataset_single, dataset_template
    