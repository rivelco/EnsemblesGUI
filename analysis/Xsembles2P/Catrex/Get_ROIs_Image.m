function [image,neuronal_mask] = Get_ROIs_Image(neurons,width,height,brightness,hues,saturation,...
                                                black_background)
% Draw ROI clusters from  neurons data (generated by catrex.m)
%
%       [image,neuronal_mask] = Get_ROIs_Image(neurons,width,height,brightness,hues,saturation,...
%                                              black_background)
%
%   default: brightness = 1; hues = 1/3; saturation = 1; black_background = true
%
% Modified by Jesus Perez-Ortega, July 2019
% Modified Oct 2019
% Modified Dec 2019
% Modified Apr 2020
% Modified Dec 2021
% Modified Feb 2023
% Modified Sep 2023 (black_background)

if nargin<7
    black_background = true;
    if nargin<6
        saturation = 1;
        if nargin<5
            hues = 1/3;
            if nargin<4
                brightness = 1;
                if nargin<3
                    error('Image height and width must be specified.')
                end
            end
        end
    end
end

n_neurons = length(neurons);
if length(brightness)==1
     brightness = brightness*ones(n_neurons,1);
end

if length(hues)==1
    hues = hues*ones(n_neurons,1);
end

if length(saturation)==1
     saturation = saturation*ones(n_neurons,1);
end

% Set value/brightness
neuronal_mask = zeros(height,width);
if black_background
    value = zeros(height,width);
    for i = 1:n_neurons
        value(neurons(i).pixels) = rescale(neurons(i).weight_pixels,0.1,0.9)*brightness(i);
        neuronal_mask(neurons(i).pixels) = i;
    end
else
    value = ones(height,width);
    for i = 1:n_neurons
        value(neurons(i).pixels) = rescale(1-neurons(i).weight_pixels,0.5,0.9)*brightness(i);
        neuronal_mask(neurons(i).pixels) = i;
    end
end

% Get hues
hue = zeros(height,width);
hue(neuronal_mask>0) = hues(neuronal_mask(neuronal_mask>0));
hue = reshape(hue,height,width);

% Get saturation
sat = zeros(height,width);
sat(neuronal_mask>0) = saturation(neuronal_mask(neuronal_mask>0));
sat = reshape(sat,height,width);

% Create image
image = hsv2rgb(cat(3,hue,sat,value));