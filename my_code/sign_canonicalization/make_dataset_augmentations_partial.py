import torch
import numpy as np
import matplotlib.pyplot as plt

import trimesh
# import my_code.diffusion_training_sign_corr.data_loading as data_loading
import my_code.datasets.shape_dataset as shape_dataset
import my_code.datasets.preprocessing as preprocessing

import os
import shutil
import utils.geometry_util as geometry_util
import utils.shape_util as shape_util
from tqdm import tqdm

import my_code.sign_canonicalization.remesh as remesh
import yaml


if __name__ == '__main__':
    
    config = {
    
        "dataset_name": "partial_isoRemesh_shot",
        
        "n_shapes": 1000,
        "lapl_type": "mesh",
        
        'descr_type': 'shot',
        'centering': 'mean',
        
        
        "split": "train",
        
        "rot_x": 0,
        "rot_y": 90,
        "rot_z": 0,
        
        "along_normal": True,
        "std": 0.0,
        "noise_clip_low": -0.05,
        "noise_clip_high": 0.05,
        
        "scale_min": 0.9,
        "scale_max": 1.1,
        
        "remesh": {
                "isotropic": {
                    "n_remesh_iters": 10,
                    "remesh_targetlen": 1,
                    "simplify_strength_min": 0.2,
                    "simplify_strength_max": 0.8,
                },
                "anisotropic": {
                    "probability": 0,
                        
                    "n_remesh_iters": 10,
                    "fraction_to_simplify_min": 0.2,
                    "fraction_to_simplify_max": 0.6,
                    "simplify_strength_min": 0.2,
                    "simplify_strength_max": 0.5,
                    "weighted_by": "face_count",
                },
                "partial": {
                    "probability": 0.8,
                    "n_remesh_iters": 10,
                    "fraction_to_keep_min": 0.5,
                    "fraction_to_keep_max": 0.8,
                    "n_seed_samples": [1, 5, 25],
                    "weighted_by": "face_count",
                },
            },
        }
    
    train_diff_folder = f'/home/s94zalek_hpc/shape_matching/data_sign_training/train/SURREAL/diffusion'
    train_dataset = shape_dataset.SingleShapeDataset(
        data_root = f'/home/s94zalek_hpc/shape_matching/data_sign_training/train/SURREAL',
        centering = 'bbox',
        num_evecs=128,
        lb_cache_dir=train_diff_folder,
        return_evecs=False
    )
    
    # prepare the folders
    base_folder = f'/lustre/mlnvme/data/s94zalek_hpc-shape_matching/data_sign_training/{config["split"]}/{config["dataset_name"]}'
    # shutil.rmtree(base_folder, ignore_errors=True)
    
    mesh_folder = f'{base_folder}/off'
    diff_folder = f'{base_folder}/diffusion'
    os.makedirs(mesh_folder)
    os.makedirs(diff_folder)
    
    # save the config
    with open(f'{base_folder}/config.yaml', 'w') as f:
        yaml.dump(config, f, sort_keys=False)
    

    iterator = tqdm(range(config["n_shapes"]))
    
    for epoch in range(config["n_shapes"] // len(train_dataset)):
        for i in range(len(train_dataset)):
        
            # get the vertices and faces                        
            verts_orig = train_dataset[i]['verts']
            faces_orig = train_dataset[i]['faces']
            
            verts, faces, _ = remesh.augmentation_pipeline_partial(
                    verts_orig,
                    faces_orig,
                    {"remesh": config["remesh"]},
                )
            
            
            
            
            # randomly choose the remeshing type
            # remesh_type = np.random.choice(['isotropic', 'partial'], p=[1-config["remesh"]["partial"]["probability"], config["remesh"]["partial"]["probability"]])
            
            # if remesh_type == 'isotropic':
            #     simplify_strength = np.random.uniform(config["remesh"]["isotropic"]["simplify_strength_min"], config["remesh"]["isotropic"]["simplify_strength_max"])
            #     verts, faces = remesh.remesh_simplify_iso(
            #         verts_orig,
            #         faces_orig,
            #         n_remesh_iters=config["remesh"]["isotropic"]["n_remesh_iters"],
            #         remesh_targetlen=config["remesh"]["isotropic"]["remesh_targetlen"],
            #         simplify_strength=simplify_strength,
            #     )
            # else:
            #     fraction_to_select = np.random.uniform(config["remesh"]["partial"]["fraction_to_select_min"], config["remesh"]["partial"]["fraction_to_select_max"])
            #     n_seed_samples = np.random.choice(config["remesh"]["partial"]["n_seed_samples"])
            #     remove_selection = n_seed_samples != 1

            #     verts, faces = remesh.remesh_partial(
            #         verts_orig,
            #         faces_orig,
            #         n_remesh_iters=config["remesh"]["partial"]["n_remesh_iters"],
            #         fraction_to_select=fraction_to_select,
            #         n_seed_samples=n_seed_samples,
            #         weighted_by=config["remesh"]["partial"]["weighted_by"],
            #         remove_selection=remove_selection
            #     )
            
            
            if config["centering"] == 'bbox':
                verts = preprocessing.center_bbox(verts)
            elif config["centering"] == 'mean':
                verts = preprocessing.center_mean(verts)
            else:
                raise ValueError(f'Invalid centering method: {config["centering"]}')
                
            # normalize vertices by area
            verts = preprocessing.normalize_face_area(verts, faces)
            


            # augment the vertices
            verts_aug = geometry_util.data_augmentation(
                verts.unsqueeze(0),
                faces.unsqueeze(0),
                rot_x=config["rot_x"],
                rot_y=config["rot_y"],
                rot_z=config["rot_z"],
                along_normal=config["along_normal"],
                std=config["std"],
                noise_clip_low=config["noise_clip_low"],
                noise_clip_high=config["noise_clip_high"],
                scale_min=config["scale_min"],
                scale_max=config["scale_max"],
                )[0]

            
            # get current iteration
            current_iteration = epoch * len(train_dataset) + i
            
            # save the mesh
            shape_util.write_off(
                f'{mesh_folder}/{current_iteration:04}.off',
                verts_aug.cpu().numpy(),
                faces.cpu().numpy()
                )
            
            
            # read the mesh again
            verts_aug, faces = shape_util.read_shape(f'{mesh_folder}/{current_iteration:04}.off')
            verts_aug = torch.tensor(verts_aug, dtype=torch.float32)
            faces = torch.tensor(faces, dtype=torch.int32)
        
            # calculate and cache the laplacian
            if config["lapl_type"] == 'pcl':
                _, _, _, _, evecs_orig, _, _ = geometry_util.get_operators(
                    verts_aug, None,
                    k=128, cache_dir=diff_folder) 
            else:               
                _, _, _, _, evecs_orig, _, _ = geometry_util.get_operators(
                    verts_aug, faces,
                    k=128, cache_dir=diff_folder)
                
                
            if config["descr_type"] == 'shot':
                import pyshot
                
                shot_descrs = pyshot.get_descriptors(
                    verts_aug.numpy().astype(np.double),
                    faces.numpy().astype(np.int64),
                    radius=100,
                    local_rf_radius=100,
                    # The following parameters are optional
                    min_neighbors=3,
                    n_bins=10,
                    double_volumes_sectors=True,
                    use_interpolation=True,
                    use_normalization=True,
                )
                
                shot_folder = f'{base_folder}/shot'
                os.makedirs(shot_folder, exist_ok=True)
                
                torch.save(
                    torch.tensor(shot_descrs),
                    f'{shot_folder}/{current_iteration:04}.pt'
                    )
                
            

            # update the iterator
            iterator.update(1)
        
