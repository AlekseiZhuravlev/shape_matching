#!/bin/bash

#SBATCH -n 1
#SBATCH -t 24:00:00
#SBATCH --array=0-17
#SBATCH --mem=50G
#SBATCH --cpus-per-task=4
#SBATCH --partition=intelsr_medium
#SBATCH --account=ag_ifi_laehner
#SBATCH --output=/home/s94zalek_hpc/shape_matching/SLURM_logs/cache_surreal_%A_%a.out
#SBATCH --error=/home/s94zalek_hpc/shape_matching/SLURM_logs/cache_surreal_%A_%a.err

source /home/s94zalek_hpc/.bashrc
conda activate fmnet
cd /home/s94zalek_hpc/shape_matching
module load libGLU Xvfb

train_worker_count=$((SLURM_ARRAY_TASK_COUNT - 1))

num_evecs=32

srun python my_code/datasets/cache_surreal_sign_corr.py  --num_evecs ${num_evecs} --n_workers ${SLURM_ARRAY_TASK_COUNT} --current_worker ${SLURM_ARRAY_TASK_ID} --net_input_type wks --evecs_per_support 4 --net_path /home/s94zalek_hpc/shape_matching/my_code/experiments/sign_double_start_0_feat_32_6block_factor4_dataset_SURREAL_train_rot_180_180_180_normal_True_noise_0.0_-0.05_0.05_lapl_mesh_scale_0.9_1.1_wks/40000.pth
# srun python my_code/datasets/cache_surreal_sign_corr_dataloader.py --num_evecs ${num_evecs} --n_workers ${SLURM_ARRAY_TASK_COUNT} --current_worker ${SLURM_ARRAY_TASK_ID} --net_input_type wks --evecs_per_support 4 --net_path /home/s94zalek_hpc/shape_matching/my_code/experiments/sign_double_start_0_feat_32_6block_factor4_dataset_SURREAL_train_rot_180_180_180_normal_True_noise_0.0_-0.05_0.05_lapl_mesh_scale_0.9_1.1_wks/40000.pth
    