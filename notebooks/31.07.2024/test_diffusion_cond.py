import torch
import numpy as np
import os
import shutil
from tqdm import tqdm
import yaml

import sys
import os

# models
from my_code.models.diag_conditional import DiagConditionedUnet
from diffusers import DDPMScheduler

# training / evaluation
from torch.utils.tensorboard import SummaryWriter
from my_code.diffusion_training_sign_corr.train_model import train_epoch
from my_code.diffusion_training_sign_corr.validate_model import validate_epoch

import my_code.diffusion_training_sign_corr.data_loading as data_loading

from my_code.datasets.surreal_cached_train_dataset import SurrealTrainDataset
import networks.diffusion_network as diffusion_network
import matplotlib.pyplot as plt
import my_code.utils.plotting_utils as plotting_utils
import utils.fmap_util as fmap_util
import metrics.geodist_metric as geodist_metric
from my_code.sign_canonicalization.training import predict_sign_change
import argparse
tqdm._instances.clear()


def parse_args():
    parser = argparse.ArgumentParser(description='Train the model')
    
    parser.add_argument('--experiment_name', type=str)
    parser.add_argument('--dataset_name', type=str)
    parser.add_argument('--split', type=str)
    
    args = parser.parse_args()
    return args


if __name__ == '__main__':

    args = parse_args()

    # configuration
    experiment_name = args.experiment_name
    checkpoint_name = 'checkpoint_99'

    ### config
    exp_base_folder = f'/home/s94zalek_hpc/shape_matching/my_code/experiments/{experiment_name}'
    with open(f'{exp_base_folder}/config.yaml', 'r') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)


    ### model
    model = DiagConditionedUnet(config["model_params"]).to('cuda')
    model.load_state_dict(torch.load(f"{exp_base_folder}/checkpoints/{checkpoint_name}.pt"))
    model = model.to('cuda')
    
    ### Sign correction network
    sign_corr_net = diffusion_network.DiffusionNet(
        in_channels=config["model_params"]["sample_size"],
        out_channels=config["model_params"]["sample_size"] // config["evecs_per_support"],
        cache_dir=None,
        input_type=config["net_input_type"],
        k_eig=128,
        n_block=6
        ).to('cuda')
    sign_corr_net.load_state_dict(
        torch.load(config["sign_net_path"]))


    ### sample the model
    noise_scheduler = DDPMScheduler(num_train_timesteps=1000, beta_schedule='squaredcos_cap_v2',
                                    clip_sample=True) 


    ### test dataset
    dataset_name = args.dataset_name
    split = args.split

    test_dataset = data_loading.get_val_dataset(
        dataset_name, split, 128
        )[1]
    sign_corr_net.cache_dir = test_dataset.lb_cache_dir


    num_evecs = config["model_params"]["sample_size"]

    ##########################################
    # Logging
    ##########################################

    log_dir = f'{exp_base_folder}/eval/{dataset_name}-{split}'
    os.makedirs(log_dir, exist_ok=True)

    fig_dir = f'{log_dir}/figs'
    os.makedirs(fig_dir, exist_ok=True)

    log_file_name = f'{log_dir}/log.txt'

    ##########################################

    ratios = []
    geo_errs = []

    Cxy_est_list = []
    C_gt_xy_corr_list = []


    data_range = tqdm(range(len(test_dataset)))

    for i in data_range:

        data = test_dataset[i]
        
        
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        # device = 'cpu'
        
        verts_first = data['first']['verts'].unsqueeze(0).to(device)
        verts_second = data['second']['verts'].unsqueeze(0).to(device)
        
        faces_first = data['first']['faces'].unsqueeze(0).to(device)
        faces_second = data['second']['faces'].unsqueeze(0).to(device)

        evecs_first = data['first']['evecs'][:, :num_evecs].unsqueeze(0).to(device)
        evecs_second = data['second']['evecs'][:, :num_evecs].unsqueeze(0).to(device)
        
        evals_first = data['first']['evals'][:num_evecs]
        evals_second = data['second']['evals'][:num_evecs]

        corr_first = data['first']['corr']
        corr_second = data['second']['corr']


        # predict the sign change
        with torch.no_grad():
            sign_pred_first, support_vector_norm_first, _ = predict_sign_change(
                sign_corr_net, verts_first, faces_first, evecs_first, 
                evecs_cond=None, input_type=sign_corr_net.input_type,
                # mass=None, L=None, evals=None, evecs=None, gradX=None, gradY=None
                mass=data['first']['mass'].unsqueeze(0), L=data['first']['L'].unsqueeze(0),
                evals=data['first']['evals'].unsqueeze(0), evecs=data['first']['evecs'].unsqueeze(0),
                gradX=data['first']['gradX'].unsqueeze(0), gradY=data['first']['gradY'].unsqueeze(0)
                )
            sign_pred_second, support_vector_norm_second, _ = predict_sign_change(
                sign_corr_net, verts_second, faces_second, evecs_second, 
                evecs_cond=None, input_type=sign_corr_net.input_type,
                # mass=None, L=None, evals=None, evecs=None, gradX=None, gradY=None
                mass=data['second']['mass'].unsqueeze(0), L=data['second']['L'].unsqueeze(0),
                evals=data['second']['evals'].unsqueeze(0), evecs=data['second']['evecs'].unsqueeze(0),
                gradX=data['second']['gradX'].unsqueeze(0), gradY=data['second']['gradY'].unsqueeze(0)
                )

        # correct the evecs
        evecs_first_corrected = evecs_first.cpu()[0] * torch.sign(sign_pred_first).cpu()
        evecs_first_corrected_norm = evecs_first_corrected / torch.norm(evecs_first_corrected, dim=0, keepdim=True)
        
        evecs_second_corrected = evecs_second.cpu()[0] * torch.sign(sign_pred_second).cpu()
        evecs_second_corrected_norm = evecs_second_corrected / torch.norm(evecs_second_corrected, dim=0, keepdim=True)
        
        # product with support
        evecs_cond_first = evecs_first_corrected_norm.transpose(0, 1) @ support_vector_norm_first[0].cpu()
        evecs_cond_second = evecs_second_corrected_norm.transpose(0, 1) @ support_vector_norm_second[0].cpu()

        # gt corrected fmap
        C_gt_xy_corr = torch.linalg.lstsq(
            evecs_second_corrected[corr_second],
            evecs_first_corrected[corr_first]
            ).solution
        
        # gt original fmap
        C_gt_xy = torch.linalg.lstsq(
            evecs_second.cpu()[0, corr_second],
            evecs_first.cpu()[0, corr_first]
            ).solution
        
        
        ###############################################
        # Conditioning
        ###############################################

        conditioning = torch.tensor([])
        
        if 'evals' in config["conditioning_types"]:
            eval = evals_second.unsqueeze(0)
            eval = torch.diag_embed(eval)
            conditioning = torch.cat((conditioning, eval), 0)
        
        if 'evals_inv' in config["conditioning_types"]:
            eval_inv = 1 / evals_second.unsqueeze(0)
            # replace elements > 1 with 1
            eval_inv[eval_inv > 1] = 1
            eval_inv = torch.diag_embed(eval_inv)
            conditioning = torch.cat((conditioning, eval_inv), 0)
        
        if 'evecs' in config["conditioning_types"]:
            evecs = torch.cat(
                (evecs_cond_first.unsqueeze(0), evecs_cond_second.unsqueeze(0)),
                0)
            conditioning = torch.cat((conditioning, evecs), 0)
        
        
        ###############################################
        # Sample the model
        ###############################################
        
        x_sampled = torch.rand(1, 1, model.model.sample_size, model.model.sample_size).to(device)
        y = conditioning.unsqueeze(0).to(device)    
        
        # print(x_sampled.shape, y.shape)
            
        # Sampling loop
        for t in noise_scheduler.timesteps:

            # Get model pred
            with torch.no_grad():
                residual = model(x_sampled, t,
                                    conditioning=y
                                    ).sample

            # Update sample with step
            x_sampled = noise_scheduler.step(residual, t, x_sampled).prev_sample

        Cxy_est = x_sampled[0][0].cpu()
        
        ###############################################
        # Evaluation
        ###############################################  
        
        # hard correspondence 
        p2p_gt = fmap_util.fmap2pointmap(
            C12=C_gt_xy,
            evecs_x=evecs_first.cpu()[0],
            evecs_y=evecs_second.cpu()[0],
            )
        p2p_corr_gt = fmap_util.fmap2pointmap(
            C12=C_gt_xy_corr,
            evecs_x=evecs_first_corrected,
            evecs_y=evecs_second_corrected,
            )
        p2p_est = fmap_util.fmap2pointmap(
            Cxy_est,
            evecs_x=evecs_first_corrected,
            evecs_y=evecs_second_corrected,
            )
        
        # distance matrices
        dist_x = torch.cdist(data['first']['verts'], data['first']['verts'])
        dist_y = torch.cdist(data['second']['verts'], data['second']['verts'])

        # geodesic error
        geo_err_gt = geodist_metric.calculate_geodesic_error(
            dist_x, data['first']['corr'], data['second']['corr'], p2p_gt, return_mean=False
            )  
        geo_err_corr_gt = geodist_metric.calculate_geodesic_error(
            dist_x, data['first']['corr'], data['second']['corr'], p2p_corr_gt, return_mean=False
            )
        geo_err_est = geodist_metric.calculate_geodesic_error(
            dist_x, data['first']['corr'], data['second']['corr'], p2p_est, return_mean=False
            )
        
        # mse between sampled and corrected fmap
        # mse_fmap = torch.nn.functional.mse_loss(C_gt_xy_corr, Cxy_est)
        mse_fmap = torch.sum((C_gt_xy_corr - Cxy_est) ** 2)
        mse_abs_fmap = torch.sum((C_gt_xy_corr.abs() - Cxy_est.abs()) ** 2)
        
        
        fig, axs = plt.subplots(1, 7, figsize=(20, 3))
        
        l = 0
        h = 32

        plotting_utils.plot_Cxy(fig, axs[0], Cxy_est,
                                f'Pred', l, h, show_grid=False, show_colorbar=False)
        plotting_utils.plot_Cxy(fig, axs[1], C_gt_xy_corr,
                                f'GT corrected', l, h, show_grid=False, show_colorbar=False)
        plotting_utils.plot_Cxy(fig, axs[2], C_gt_xy,
                                f'GT orig', l, h, show_grid=False, show_colorbar=False)
        plotting_utils.plot_Cxy(fig, axs[3], Cxy_est - C_gt_xy_corr,
                                f'Error', l, h, show_grid=False, show_colorbar=False)
        plotting_utils.plot_Cxy(fig, axs[4], Cxy_est.abs() - C_gt_xy_corr.abs(),
                                f'Error abs', l, h, show_grid=False, show_colorbar=False)
        plotting_utils.plot_Cxy(fig, axs[5], evecs_cond_first,
                                f'evecs cond first', l, h, show_grid=False, show_colorbar=False)
        plotting_utils.plot_Cxy(fig, axs[6], evecs_cond_second,
                                f'evecs cond second', l, h, show_grid=False, show_colorbar=False)
        
        # replace code above with writing to log file
        with open(log_file_name, 'a') as f:
            f.write(f'{i}\n')
            f.write(f'Geo error GT: {geo_err_gt.mean() * 100:.2f}\n')
            f.write(f'Geo error GT corr: {geo_err_corr_gt.mean() * 100:.2f}\n')
            f.write(f'Geo error est: {geo_err_est.mean() * 100:.2f}\n')
            f.write(f'MSE fmap: {mse_fmap:.3f}\n')
            f.write(f'MSE abs fmap: {mse_abs_fmap:.3f}\n')
            f.write('-----------------------------------\n')
        
        # break
        plt.savefig(f'{fig_dir}/{i}.png')
        plt.close()
        
        # print(f'{i:2d}) ratio {geo_err_est.mean() / geo_err_corr_gt.mean():.2f}')
        
        ratio_curr = geo_err_est.mean() / geo_err_corr_gt.mean()
        geo_err_curr = geo_err_est.mean() * 100
        
        ratios.append(ratio_curr)
        geo_errs.append(geo_err_curr)
        Cxy_est_list.append(Cxy_est)
        C_gt_xy_corr_list.append(C_gt_xy_corr)
        
        # data_range.set_description(
        #     f'Geo error est: {geo_err_curr:.2f}, '+\
        #     f'Mean {torch.tensor(geo_errs).mean():.2f}, '+\
        #     f'Median {torch.tensor(geo_errs).median():.2f}, '+\
        #     f'Ratio: {ratio_curr:.2f}, '+\
        #     f'Mean: {torch.tensor(ratios).mean():.2f}, '+\
        #     f'Median: {torch.tensor(ratios).median():.2f}'
        #     )
    

    ratios = torch.tensor(ratios)
    geo_errs = torch.tensor(geo_errs)
        
    # replace code above with writing to log file
    with open(log_file_name, 'a') as f:
        f.write('-----------------------------------\n')
        f.write('Total statistics\n')
        f.write('-----------------------------------\n')
        f.write(f'Mean geo err: {geo_errs.mean():.2f}\n')
        f.write(f'Median geo err: {geo_errs.median():.2f}\n')
        f.write(f'Min geo err: {geo_errs.min():.2f}\n')
        f.write(f'Max geo err: {geo_errs.max():.2f}\n')
        f.write('\n')
        f.write(f'Mean ratio: {ratios.mean():.2f}\n')
        f.write(f'Median ratio: {ratios.median():.2f}\n')
        f.write(f'Min ratio: {ratios.min():.2f}\n')
        f.write(f'Max ratio: {ratios.max():.2f}\n')
        f.write('\n')
        f.write('-----------------------------------\n')