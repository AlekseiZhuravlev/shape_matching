import os
import numpy as np
import shutil

import torch
from tqdm import tqdm
import argparse
import time

import sys
import os
curr_dir = os.getcwd()
if 's94zalek_hpc' in curr_dir:
    user_name = 's94zalek_hpc'
else:
    user_name = 's94zalek'
sys.path.append(f'/home/{user_name}/shape_matching/')

from my_code.sign_canonicalization.training import predict_sign_change
import networks.diffusion_network as diffusion_network
import my_code.utils.plotting_utils as plotting_utils
import matplotlib.pyplot as plt

import my_code.datasets.shape_dataset as shape_dataset
import my_code.datasets.template_dataset as template_dataset
    
    
def visualize_before_after(data, C_xy_corr, evecs_cond_first, evecs_cond_second, figures_folder, idx):
        l = 0
        h = 32

        fig, axs = plt.subplots(1, 5, figsize=(18, 5))

        plotting_utils.plot_Cxy(fig, axs[0], data['second']['C_gt_xy'][0],
                                'before', l, h, show_grid=False, show_colorbar=False)
        plotting_utils.plot_Cxy(fig, axs[1], C_xy_corr,
                                'after', l, h, show_grid=False, show_colorbar=False)
        plotting_utils.plot_Cxy(fig, axs[2], data['second']['C_gt_xy'][0, l:h, l:h] - C_xy_corr,
                        'diff', l, h, show_grid=False, show_colorbar=False)
        plotting_utils.plot_Cxy(fig, axs[3], data['second']['C_gt_xy'][0, l:h, l:h].abs() - C_xy_corr.abs(),
                        'abs diff', l, h, show_grid=False, show_colorbar=False)
        plotting_utils.plot_Cxy(fig, axs[3], evecs_cond_first,
                        'evecs_cond_first', l, h, show_grid=False, show_colorbar=False)
        plotting_utils.plot_Cxy(fig, axs[4], evecs_cond_second,
                        'evecs_cond_second', l, h, show_grid=False, show_colorbar=False)

        # save the figure
        fig.savefig(f'{figures_folder}/{idx}.png')
        plt.close(fig)
        
    
def get_corrected_data(data, num_evecs, net, net_input_type):
    
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    # device = 'cpu'
    
    verts_first = data['first']['verts'].to(device)
    verts_second = data['second']['verts'].to(device)
    
    faces_first = data['first']['faces'].to(device)
    faces_second = data['second']['faces'].to(device)

    evecs_first = data['first']['evecs'][:,:, :num_evecs].to(device)
    evecs_second = data['second']['evecs'][:,:, :num_evecs].to(device)

    corr_first = data['first']['corr']
    corr_second = data['second']['corr']


    # predict the sign change
    with torch.no_grad():
        sign_pred_first = predict_sign_change(
            net, verts_first, faces_first, evecs_first, 
            evecs_cond=None, input_type=net_input_type,
            # mass=None, L=None, evals=None, evecs=None, gradX=None, gradY=None
            mass=data['first']['mass'], L=data['first']['L'],
            evals=data['first']['evals'], evecs=data['first']['evecs'],
            gradX=data['first']['gradX'], gradY=data['first']['gradY'],
            )[0]
        sign_pred_second = predict_sign_change(
            net, verts_second, faces_second, evecs_second, 
            evecs_cond=None, input_type=net_input_type,
            # mass=None, L=None, evals=None, evecs=None, gradX=None, gradY=None
            mass=data['second']['mass'], L=data['second']['L'],
            evals=data['second']['evals'], evecs=data['second']['evecs'],
            gradX=data['second']['gradX'], gradY=data['second']['gradY'],
            )[0]

    # correct the evecs
    
    evecs_first_corrected = evecs_first.cpu()[0] * torch.sign(sign_pred_first).cpu()
    evecs_first_corrected = evecs_first_corrected / torch.norm(evecs_first_corrected, dim=0, keepdim=True)
    
    evecs_second_corrected = evecs_second.cpu()[0] * torch.sign(sign_pred_second).cpu()
    evecs_second_corrected = evecs_second_corrected / torch.norm(evecs_second_corrected, dim=0, keepdim=True)
    
    # product with itself
    evecs_cond_first = evecs_first_corrected.transpose(0, 1) @ evecs_first_corrected
    evecs_cond_second = evecs_second_corrected.transpose(0, 1) @ evecs_second_corrected

    # correct the functional map
    C_xy_pred = torch.linalg.lstsq(
        evecs_second.cpu()[0, corr_second[0]] * torch.sign(sign_pred_second).cpu(),
        evecs_first.cpu()[0, corr_first[0]] * torch.sign(sign_pred_first).cpu()
        ).solution

    return C_xy_pred, evecs_cond_first, evecs_cond_second
    
    
    

def save_train_dataset(
        dataloader,
        dataset_folder,
        start_idx,
        end_idx,
        num_evecs,
        **net_params
    ):
    
    curr_time = time.time()
    
    train_folder = f'{dataset_folder}/train'
    os.makedirs(train_folder, exist_ok=True)
    
    figures_folder = f'{train_folder}/figures'
    os.makedirs(figures_folder, exist_ok=True)

    evals_file = os.path.join(train_folder, f'evals_{start_idx}_{end_idx}.txt')
    fmaps_file = os.path.join(train_folder, f'C_gt_xy_{start_idx}_{end_idx}.txt')
    evecs_cond_first_file = os.path.join(train_folder, f'evecs_cond_first_{start_idx}_{end_idx}.txt')
    evecs_cond_second_file = os.path.join(train_folder, f'evecs_cond_second_{start_idx}_{end_idx}.txt')
    
    # remove if exists    
    for file_type in [evals_file, fmaps_file, evecs_cond_first_file, evecs_cond_second_file]:
        if os.path.exists(file_type):
            print(f'Removing {file_type}')
            os.remove(file_type)
    
    print(f'Saving evals to {evals_file}', f'fmaps to {fmaps_file}', f'evecs_cond to {evecs_cond_first_file}')
    
    for i, data in enumerate(dataloader):
        
        evals = data['second']['evals'][:,:num_evecs]
        C_xy_corr, evecs_cond_first, evecs_cond_second = get_corrected_data(
            data=data,
            num_evecs=num_evecs,
            **net_params
        )
                
        with open(fmaps_file, 'ab') as f:
            np.savetxt(f, C_xy_corr.numpy().flatten().astype(np.float32), newline=" ")
            f.write(b'\n')
            
        with open(evals_file, 'ab') as f:
            np.savetxt(f, evals.numpy().astype(np.float32), newline=" ")
            f.write(b'\n')
            
        with open(evecs_cond_first_file, 'ab') as f:
            np.savetxt(f, evecs_cond_first.numpy().flatten().astype(np.float32), newline=" ")
            f.write(b'\n')
            
        with open(evecs_cond_second_file, 'ab') as f:
            np.savetxt(f, evecs_cond_second.numpy().flatten().astype(np.float32), newline=" ")
            f.write(b'\n')
        
            
        if i % 100 == 0 or i == 25:
            time_elapsed = time.time() - curr_time
            print(f'{i}/{len(train_indices)}, time: {time_elapsed:.2f}, avg: {time_elapsed / (i + 1):.2f}',
                  flush=True)
            
        if i < 5 or i % 1000 == 0:
            visualize_before_after(
                data, C_xy_corr,
                evecs_cond_first, evecs_cond_second,
                figures_folder, start_idx + i)


def parse_args():
    
    parser = argparse.ArgumentParser()
    
    parser.add_argument('--n_workers', type=int)
    parser.add_argument('--current_worker', type=int)
    
    parser.add_argument('--num_evecs', type=int)
    
    parser.add_argument('--net_path', type=str)
    parser.add_argument('--net_input_type', type=str)
    parser.add_argument('--evecs_per_support', type=int)
    
    args = parser.parse_args()
    
    # python my_code/datasets/cache_surreal_sign_corr_dataloader.py --n_workers 1 --current_worker 0 --num_evecs 32 --net_input_type wks --evecs_per_support 4 --net_path /home/s94zalek_hpc/shape_matching/my_code/experiments/sign_double_start_0_feat_32_6block_factor4_dataset_SURREAL_train_rot_180_180_180_normal_True_noise_0.0_-0.05_0.05_lapl_mesh_scale_0.9_1.1_wks/40000.pth
    
    return args
         
         
if __name__ == '__main__':
    
    args = parse_args()

    np.random.seed(120)
    
    num_evecs = args.num_evecs
        
    ####################################################
    # Dataset
    ####################################################
    
    from my_code.datasets.surreal_dataset_3dc import TemplateSurrealDataset3DC
    
    if not os.path.exists('/tmp/mmap_datas_surreal_train.pth'):
        
        print('Copying the file to /tmp', flush=True)
        #rsync -aq /home/s94zalek_hpc/3D-CODED/data/mmap_datas_surreal_train.pth /tmp/
        os.system('rsync -aq /home/s94zalek_hpc/3D-CODED/data/mmap_datas_surreal_train.pth /tmp/')
        
        assert os.path.exists('/tmp/mmap_datas_surreal_train.pth')

    
    dataset = TemplateSurrealDataset3DC(
        # shape_path=f'/home/s94zalek_hpc/3D-CODED/data/mmap_datas_surreal_train.pth',
        # shape_path='/lustre/mlnvme/data/s94zalek_hpc-shape_matching/mmap_datas_surreal_train.pth',
        shape_path=f'/tmp/mmap_datas_surreal_train.pth',
        num_evecs=128,
        use_cuda=False,
        cache_lb_dir=None,
        return_evecs=True,
        mmap=True
    )    
    
    print('Dataset created', flush=True)
    
    # sample train/test indices
    train_indices = list(range(len(dataset)))
    print(f'Number of training samples: {len(train_indices)}', flush=True)
    
    # folder to store the dataset
    # dataset_name = f'dataset_3dc_correctedSecond_noAug_{num_evecs}'
    dataset_name = f'dataset_SURREAL_train_withAug_productSuppCond_{num_evecs}'
    dataset_folder = f'/home/{user_name}/shape_matching/data/SURREAL_full/full_datasets/{dataset_name}'
    # shutil.rmtree(dataset_folder, ignore_errors=True)
    os.makedirs(dataset_folder, exist_ok=True)
    
    
    ####################################################
    # Sign correction network
    ####################################################

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    # device = 'cpu'
    net = diffusion_network.DiffusionNet(
        in_channels=num_evecs,
        out_channels=num_evecs // args.evecs_per_support,
        cache_dir=None,
        input_type=args.net_input_type,
        k_eig=128,
        n_block=6
        ).to(device)
    
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    net.load_state_dict(torch.load(args.net_path, map_location=device))
    
    ####################################################
    # Saving
    ####################################################

    # current and total workers
    n_workers = args.n_workers
    current_worker = args.current_worker
    
    # samples per worker
    n_samples = len(train_indices)
    samples_per_worker = n_samples // n_workers
    
    # start - end indices
    start = current_worker * samples_per_worker
    end = (current_worker + 1) * samples_per_worker
    if current_worker == n_workers - 1:
        end = n_samples
        
    print(f'Worker {current_worker} processing samples from {start} to {end}', flush=True)
    
    # indices for this worker
    train_indices = train_indices[start:end]
    
    subset = torch.utils.data.Subset(dataset, train_indices)
    dataloader = torch.utils.data.DataLoader(
        subset, batch_size=1, shuffle=False,
        num_workers=4,
        pin_memory=False
    )

    print(f"Saving train dataset...", flush=True)
    save_train_dataset(
        dataloader=dataloader,
        dataset_folder=dataset_folder,
        start_idx=start,
        end_idx=end,
        num_evecs=num_evecs,
        
        # sign corr net parameters
        net=net,
        net_input_type=args.net_input_type
    )
