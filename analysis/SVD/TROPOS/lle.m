% LLE ALGORITHM (using K nearest neighbors)
%
% [Y] = lle(X,K,dmax)
%
% X = data as D x N matrix (D = dimensionality, N = #points)
% K = number of neighbors
% dmax = max embedding dimensionality
% Y = embedding as dmax x N matrix

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

function [Y,DiMatrix] = lle(X,K,d)

[D,N] = size(X);
fprintf(1,'LLE running on %d points in %d dimensions\n',N,D);


% STEP1: COMPUTE PAIRWISE DISTANCES & FIND NEIGHBORS 
fprintf(1,'-->Finding %d nearest neighbours.\n',K);

X2 = sum(X.^2,1);
distance = repmat(X2,N,1)+repmat(X2',1,N)-2*X'*X;

[sorted,index] = sort(distance);
neighborhood = index(2:(1+K),:);

% STEP2: SOLVE FOR RECONSTRUCTION WEIGHTS
fprintf(1,'-->Solving for reconstruction weights.\n');
LC=0.000001;

if(K>D) 
  fprintf(1,'   [note: K>D; regularization will be used]\n'); 
  tol=1e-3; % regularlizer in case constrained fits are ill conditioned
else
  tol=0+LC;
end

W = zeros(K,N);
for ii=1:N
   z = X(:,neighborhood(:,ii))-repmat(X(:,ii),1,K)+LC; % shift ith pt to origin
   C = z'*z;                                        % local covariance
   % other possible regularizers for K>D
%   C = C + tol*diag(diag(C));                       % regularlization
%    C = C + eye(K,K)*tol*trace(C)*K;                 % regularlization
   C = C + eye(K,K)*tol*trace(C);                   % regularlization (K>D)
   W(:,ii) = C\ones(K,1);                           % solve Cw=1
   W(:,ii) = W(:,ii)/sum(W(:,ii));                  % enforce sum(w)=1
end;

% STEP 3: COMPUTE EMBEDDING FROM EIGENVECTS OF COST MATRIX M=(I-W)'(I-W)
fprintf(1,'-->Computing embedding.\n');

% M=eye(N,N); % use a sparse matrix with storage for 4KN nonzero elements
M = sparse(1:N,1:N,ones(1,N),N,N,4*K*N); 
for ii=1:N
   w = W(:,ii);
   jj = neighborhood(:,ii);
   M(ii,jj) = M(ii,jj) - w';
   M(jj,ii) = M(jj,ii) - w;
   M(jj,jj) = M(jj,jj) + w*w';
end;

% CALCULATION OF EMBEDDING
 options.disp = 0; options.isreal = 1; options.issym = 1; 
  [Y,eigenvals,flag] = eigs(M,d+1,0,options);
% [Y,eigenvals] = eig(full(M)); %para mejorar la visualizacion 
% flag=0;
fprintf(1,'Done eigen.\n');

if (flag==0)    %S�lo si los eigenvectors convergen
    Y = Y(:,2:d+1)'*sqrt(N); % bottom evect is [1,1,1,1...] with eval 0    
else
    Y=0;
end

DiMatrix=distance;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


% other possible regularizers for K>D
%   C = C + tol*diag(diag(C));                       % regularlization
%   C = C + eye(K,K)*tol*trace(C)*K;                 % regularlization
