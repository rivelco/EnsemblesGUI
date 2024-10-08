function [results] =  raster2ens_by_density(raster,pars)
% raster = N x T binary matrix
% pars is a structure with the following parameters

% Reference paper: Herzog et al. 2020 "Scalable and accurate automated method 
% for neuronal ensemble detection in spiking neural networks"
% https://www.biorxiv.org/content/10.1101/2020.10.12.335901v1
% Rub�n Herzog October 2020

% 1.- parameters definitions
if ~isfield(pars,'npcs') || isempty(pars.npcs)
    pars.npcs = 6;
end
if ~isfield(pars,'dc') || isempty(pars.dc)
    pars.dc = 0.02;
end
if ~isfield(pars,'minspk') || isempty(pars.minspk)
    pars.minspk = 3;
end
if ~isfield(pars,'minsize') || isempty(pars.minsize)
    pars.minsize = 3;
end
if ~isfield(pars,'cent_thr') || isempty(pars.cent_thr)
    pars.cent_thr = 99.9;
end
if ~isfield(pars,'nsur') || isempty(pars.nsur)
    pars.nsur = 100;
end
if ~isfield(pars,'prct') || isempty(pars.prct)
    pars.prct = 99.9;
end
if ~isfield(pars,'inner_corr') || isempty(pars.inner_corr)
    pars.inner_corr = 0;
end

% 2.- Selection of bins
disp("> Selecting timepoints...")
[N,T] = size(raster);
selbins = sum(raster)>pars.minspk;
ras=raster(:,selbins)*1;

% 3.- pca and distance matrix
disp("> Calculating PCA and distance matrix...")
[~,pcs,~,~,exp_var] = pca(ras'); % pca with npcs num components
pcs = pcs(:,1:pars.npcs);
bincor = pdist2(pcs,pcs); % euclidean distance on principal component space

% 4.- rho and delta computation
disp("> Rho and delta computation...")
[~, rho] = paraSetv2(bincor, pars.dc);
delta = delta_from_dist_mat(bincor, rho);
[Nens,cents,predbounds] = cluster_by_pow_fit(delta,rho,pars.cent_thr);
if Nens==1
    labels = ones(length(delta),1);
else
    dist2cent = bincor(cents>0,:); % distance from centroid to any other point
    [~,labels] = min(dist2cent);
end

% 5.- ensemble raster
disp("> Calculating ensemble raster...")
ensmat_out = zeros(Nens,T);
ensmat_out(:,selbins) = bsxfun(@eq,labels',(1:Nens))';

% 6.- core-cells computation
disp("> Core-cells computation...")
[core_cells,~,ens_cel_corr,sur_cel_cor] = find_core_cells_by_correlation(raster,ensmat_out,pars.nsur,pars.prct);
id_sel_core = sum(core_cells,1)>pars.minsize;

% 7.- filtering core cells
disp("> Filtering core cells...")
[ens_corr,corr_thr,corr_selection] = filter_ens_by_inner_corr(raster,core_cells,pars.inner_corr);
final_sel_ens = corr_selection & id_sel_core;

% 8.- final ensemble outputs
disp("> Final ensemble filtering...")
sel_ensmat_out = ensmat_out(final_sel_ens,:); % filtering by magnitude &  inner cell correlation
sel_core_cells = core_cells(:,final_sel_ens);
Nens_final = size(sel_ensmat_out,1);
if Nens_final>1
    sel_labels = sum(bsxfun(@times,sel_ensmat_out,(1:Nens_final)'));
else
    sel_labels = bsxfun(@times,sel_ensmat_out,(1:Nens_final)');
end

% Pack results
disp("> Packing final results...")
% Remove low magnitude pop events
results.active_raster = ras;
results.selbins = selbins;
% PCA and distance matrix
results.exp_var = exp_var;
results.pcs = pcs;
results.bincor = bincor;
% Rho and delta computation
results.rho = rho;
results.delta = delta;
results.Nens = Nens;
results.cents = cents;
results.predbounds = predbounds;
results.labels = labels;
% Ensemble raster
results.ensmat_out = ensmat_out;
% Core cells computation
results.core_cells = core_cells;
results.ens_cel_corr = ens_cel_corr;
results.sur_cel_cor = sur_cel_cor;
results.id_sel_core = id_sel_core;
% Filtering core cells
results.ens_corr = ens_corr;
results.corr_thr = corr_thr;
results.corr_selection = corr_selection;
results.final_sel_ens = final_sel_ens;
% Final ensemble outputs
results.sel_ensmat_out = sel_ensmat_out;
results.sel_core_cells = sel_core_cells;
results.Nens_final = Nens_final;
results.sel_labels = sel_labels;
