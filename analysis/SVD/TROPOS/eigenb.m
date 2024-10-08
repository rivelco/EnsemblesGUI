function  varargout = eigenb(varargin)
%EIGS  Find a few eigenvalues and eigenvectors of a matrix using ARPACK.
%   D = EIGS(A) returns a vector of A's 6 largest magnitude eigenvalues.
%   A must be square and should be large and sparse.
%
%   [V,D] = EIGS(A) returns a diagonal matrix D of A's 6 largest magnitude
%   eigenvalues and a matrix V whose columns are the corresponding eigenvectors.
%
%   [V,D,FLAG] = EIGS(A) also returns a convergence flag.  If FLAG is 0
%   then all the eigenvalues converged; otherwise not all converged.
%
%   EIGS(AFUN,N) accepts the function AFUN instead of the matrix A.
%   Y = AFUN(X) should return Y = A*X.  N is the size of A.  The matrix A
%   represented by AFUN is assumed to be real and nonsymmetric.  In all these
%   calling sequences, EIGS(A,...) may be replaced by EIGS(AFUN,N,...).
%
%   EIGS(A,B) solves the generalized eigenvalue problem A*V == B*V*D.  B must
%   be symmetric (or Hermitian) positive definite and the same size as A.
%   EIGS(A,[],...) indicates the standard eigenvalue problem A*V == V*D.
%
%   EIGS(A,K) and EIGS(A,B,K) return the K largest magnitude eigenvalues.
%
%   EIGS(A,K,SIGMA) and EIGS(A,B,K,SIGMA) return K eigenvalues based on SIGMA:
%      'LM' or 'SM' - Largest or Smallest Magnitude
%   For real symmetric problems, SIGMA may also be:
%      'LA' or 'SA' - Largest or Smallest Algebraic
%      'BE' - Both Ends, one more from high end if K is odd
%   For nonsymmetric and complex problems, SIGMA may also be:
%      'LR' or 'SR' - Largest or Smallest Real part
%      'LI' or 'SI' - Largest or Smallest Imaginary part
%   If SIGMA is a real or complex scalar, EIGS finds the eigenvalues closest to
%   SIGMA.  In this case, B need only be symmetric (or Hermitian) positive
%   semi-definite and the function Y = AFUN(X) must return Y = (A-SIGMA*B)\X.
%
%   EIGS(A,K,SIGMA,OPTS) and EIGS(A,B,K,SIGMA,OPTS) specify options:
%   OPTS.issym: symmetry of A or A-SIGMA*B represented by AFUN [{0} | 1]
%   OPTS.isreal: complexity of A or A-SIGMA*B represented by AFUN [0 | {1}]
%   OPTS.tol: convergence: abs(d_comp-d_true) < tol*abs(d_comp) [scalar | {eps}]
%   OPTS.maxit: maximum number of iterations [integer | {300}]
%   OPTS.p: number of Lanczos vectors: K+1<p<=N [integer | {2K}]
%   OPTS.v0: starting vector [N-by-1 vector | {randomly generated by ARPACK}]
%   OPTS.disp: diagnostic information display level [0 | {1} | 2]
%   OPTS.cholB: B is actually its Cholesky factor CHOL(B) [{0} | 1]
%   OPTS.permB: sparse B is actually CHOL(B(permB,permB)) [permB | {1:N}]
%
%   EIGS(AFUN,N,K,SIGMA,OPTS,P1,...) and EIGS(AFUN,N,B,K,SIGMA,OPTS,P1,...)
%   provide for additional arguments which are passed to AFUN(X,P1,...).
%
%   Examples:
%      A = delsq(numgrid('C',15));  d1 = eigs(A,5,'SM');
%   Equivalently, if dnRk is the following one-line function:
%      function y = dnRk(x,R,k)
%      y = (delsq(numgrid(R,k))) * x;
%   then pass dnRk's additional arguments, 'C' and 15, to eigs:
%      n = size(A,1);  opts.issym = 1;  d2 = eigs(@dnRk,n,5,'SM',opts,'C',15);
%
%   See also EIG, SVDS, ARPACKC.

%   Copyright 1984-2000 The MathWorks, Inc.
%   $Revision: 1.38 $  $Date: 2000/08/02 21:50:54 $

cputms = zeros(5,1);
t0 = cputime; % start timing pre-processing

if (nargout > 3)
    error('Too many output arguments')
end

% Process inputs and do error-checking
if isa(varargin{1},'double')
    A = varargin{1};
    Amatrix = 1;
else
	A = fcnchk(varargin{1});
    Amatrix = 0;
end

isrealprob = 1; % isrealprob = isreal(A) & isreal(B) & isreal(sigma)
if Amatrix
    isrealprob = isreal(A);
end

issymA = 0;
if Amatrix
    issymA = isequal(A,A');
end

if Amatrix
    [m,n] = size(A);
    if (m ~= n)
        error('A must be a square matrix or a function which computes A*x')
    end
else
    n = varargin{2};
    nstr = sprintf('Size of problem n must be a positive integer');
    if ~isequal(size(n),[1,1]) | ~isreal(n)
        error(nstr)
    end
    if (round(n) ~= n)
        warning(nstr)
        n = round(n);
    end
    if issparse(n)
        n = full(n);
    end
end

Bnotthere = 0;
Bstr = sprintf(['Generalized matrix B must be the same size as A and' ...
        ' either a symmetric positive (semi-)definite matrix or' ...
        ' its Cholesky factor']);
if (nargin < (3-Amatrix-Bnotthere))
    B = [];
    Bnotthere = 1;
else
    Bk = varargin{3-Amatrix-Bnotthere};
    if isempty(Bk) % allow eigs(A,[],k,sigma,opts);
        B = Bk;
    else
        if isequal(size(Bk),[1,1]) & (n ~= 1)
            B = [];
            k = Bk;
            Bnotthere = 1;
        else % eigs(9,8,...) assumes A=9, B=8, ... NOT A=9, k=8, ...
            B = Bk;
            if ~isa(B,'double') | ~isequal(size(B),[n,n])
                error(Bstr)
            end
            isrealprob = isrealprob & isreal(B);
        end
    end
end

if Amatrix & ((nargin - ~Bnotthere)>4)
    error('Too many inputs')
end

if (nargin < (4-Amatrix-Bnotthere))
    k = min(n,6);
else
    k = varargin{4-Amatrix-Bnotthere};
end

kstr = sprintf(['Number of eigenvalues requested k must be a' ...
        ' positive integer <= n']);
if ~isa(k,'double') | ~isequal(size(k),[1,1]) | ~isreal(k) | (k>n)
    error(kstr)
end
if issparse(k)
    k = full(k);
end
if (round(k) ~= k)
    warning(kstr)
    k = round(k);
end

whchstr = sprintf(['Eigenvalue range sigma must be a valid 2-element string']);
if (nargin < (5-Amatrix-Bnotthere))
    whch = 'LM';
    sigma = 0;
else
    whch = varargin{5-Amatrix-Bnotthere};
    if isstr(whch)
        if ~isequal(size(whch),[1,2])
            error(whchstr)
        end
        whch = upper(whch);
        sigma = 0;
    else
        sigma = whch;
        if ~isa(sigma,'double') | ~isequal(size(sigma),[1,1])
            error('Eigenvalue shift sigma must be a scalar')
        end
        if issparse(sigma)
            sigma = full(sigma);
        end
        isrealprob = isrealprob & isreal(sigma);
        if (sigma == 0)
            whch = 'SM';
        else
            whch = 'LM';
        end
    end
end

tol = eps; % ARPACK's minimum tolerance is eps/2 (DLAMCH's EPS)
maxit = [];
p = [];
info = int32(0); % use a random starting vector
display = 1;
cholB = 0;

if (nargin >= (6-Amatrix-Bnotthere))
    opts = varargin{6-Amatrix-Bnotthere};
    if ~isa(opts,'struct')
        error('Options argument must be a structure')
    end
    
    if isfield(opts,'issym') & ~Amatrix
        issymA = opts.issym;
        if (issymA ~= 0) & (issymA ~= 1)
            error('opts.issym must be 0 or 1')
        end
    end
    
    if isfield(opts,'isreal') & ~Amatrix
        if (opts.isreal ~= 0) & (opts.isreal ~= 1)
            error('opts.isreal must be 0 or 1')
        end
        isrealprob = isrealprob & opts.isreal;
    end
    
    if ~isempty(B) & (isfield(opts,'cholB') | isfield(opts,'permB'))
        if isfield(opts,'cholB')
            cholB = opts.cholB;
            if (cholB ~= 0) & (cholB ~= 1)
                error('opts.cholB must be 0 or 1')
            end
            if isfield(opts,'permB')
                if issparse(B) & cholB
                    permB = opts.permB;
                    if ~isequal(sort(permB),(1:n)) & ...
                            ~isequal(sort(permB),(1:n)')
                        error('opts.permB must be a permutation of 1:n')
                    end
                else
                    warning(['Ignoring opts.permB since B is not its sparse' ...
                            ' Cholesky factor'])
                end
            else
                permB = 1:n;
            end
        end
    end
    
    if isfield(opts,'tol')
        if ~isequal(size(opts.tol),[1,1]) | ~isreal(opts.tol) | (opts.tol<=0)
            error(['Convergence tolerance opts.tol must be a strictly' ...
                    ' positive real scalar'])
        else
            tol = full(opts.tol);
        end
    end
    
    if isfield(opts,'p')
        p = opts.p;
        pstr = sprintf(['Number of basis vectors opts.p must be a positive' ...
                ' integer <= n']);
        if ~isequal(size(p),[1,1]) | ~isreal(p) | (p<=0) | (p>n)
            error(pstr)
        end
        if issparse(p)
            p = full(p);
        end
        if (round(p) ~= p)
            warning(pstr)
            p = round(p);
        end
    end
    
    if isfield(opts,'maxit')
        maxit = opts.maxit;
        str = sprintf(['Maximum number of iterations opts.maxit must be' ...
                ' a positive integer']);
        if ~isequal(size(maxit),[1,1]) | ~isreal(maxit) | (maxit<=0)
            error(str)
        end
        if issparse(maxit)
            maxit = full(maxit);
        end
        if (round(maxit) ~= maxit)
            warning(str)
            maxit = round(maxit);
        end
    end
    
    if isfield(opts,'v0')
        if ~isequal(size(opts.v0),[n,1])
            error('Start vector opts.v0 must be n-by-1')
        end
        if isrealprob
            if ~isreal(opts.v0)
                error(['Start vector opts.v0 must be real for real problems'])
            end
            resid = full(opts.v0);
        else
            resid(1:2:(2*n-1),1) = full(real(opts.v0));
            resid(2:2:2*n,1) = full(imag(opts.v0));
        end
        info = int32(1); % use resid as starting vector
    end
    
    if isfield(opts,'disp')
        display = opts.disp;
        dispsyt = sprintf('Diagnostic level opts.disp must be an integer');
        if (~isequal(size(display),[1,1])) | (~isreal(display)) | (display<0)
            error(dispstr)
        end
        if (round(display) ~= display)
            warning(dispstr)
            display = round(display);
        end
    end
    
    if isfield(opts,'cheb')
        warning(['Ignoring polynomial acceleration opts.cheb' ...
                ' (no longer an option)']);
    end
    if isfield(opts,'stagtol')
        warning(['Ignoring stagnation tolerance opts.stagtol' ...
                ' (no longer an option)']);
    end
    
end

% Now we know issymA, isrealprob, cholB, and permB

if isempty(p)
    if isrealprob & ~issymA
        p = min(max(2*k+1,20),n);
    else
        p = min(max(2*k,20),n);
    end
end
if isempty(maxit)
    maxit = max(300,ceil(2*n/max(p,1)));
end
if (info == int32(0))
    if isrealprob
        resid = zeros(n,1);
    else
        resid = zeros(2*n,1);
    end
end

if ~isempty(B) % B must be symmetric (Hermitian) positive (semi-)definite
    if cholB
        if ~isequal(triu(B),B)
            error(Bstr)
        end
    else
        if ~isequal(B,B')
            error(Bstr)
        end
    end
end

useeig = 0;
if isrealprob & issymA
    knstr = sprintf(['For real symmetric problems, must have number' ...
            ' of eigenvalues k < n.\n']);
else
    knstr = sprintf(['For nonsymmetric and complex problems, must have' ...
            ' number of eigenvalues k < n-1.\n']);
end
if isempty(B)
    knstr = [knstr sprintf(['Using eig(full(A)) instead.'])];
else
    knstr = [knstr sprintf(['Using eig(full(A),full(B)) instead.'])];
end
if (k == 0)
    useeig = 1;
end
if isrealprob & issymA
    if (k > n-1)
        if (n >= 6)
            warning(knstr)
        end
        useeig = 1;
    end
else
    if (k > n-2)
        if (n >= 7)
            warning(knstr)
        end
        useeig = 1;
    end
end

if isrealprob & issymA
    if ~isreal(sigma)
        error(['For real symmetric problems, eigenvalue shift sigma must' ...
                ' be real'])
    end
else
    if ~isrealprob & issymA & ~isreal(sigma)
        warning(['Complex eigenvalue shift sigma on a Hermitian problem' ...
                ' (all real eigenvalues)'])
    end
end

if isrealprob & issymA
    if strcmp(whch,'LR')
        whch = 'LA';
        warning(['For real symmetric problems, sigma value ''LR''' ...
                ' (Largest Real) is now ''LA'' (Largest Algebraic)'])
    end
    if strcmp(whch,'SR')
        whch = 'SA';
        warning(['For real symmetric problems, sigma value ''SR''' ...
                ' (Smallest Real) is now ''SA'' (Smallest Algebraic)'])
    end
    if ~ismember(whch,{'LM', 'SM', 'LA', 'SA', 'BE'})
        error(whchstr)
    end
else
    if strcmp(whch,'BE')
        warning(['Sigma value ''BE'' is now only available for real' ...
                ' symmetric problems.  Computing ''LM'' eigenvalues instead.'])
        whch = 'LM';
    end
    if ~ismember(whch,{'LM', 'SM', 'LR', 'SR', 'LI', 'SI'})
        error(whchstr)
    end
end

% Now have enough information to do early return on cases eigs does not handle
if useeig
    if (nargout <= 1)
        varargout{1} = eigs2(A,n,B,k,whch,sigma,cholB, ...
            varargin{7-Amatrix-Bnotthere:end});
    else
        [varargout{1},varargout{2}] = eigs2(A,n,B,k,whch,sigma,cholB, ...
            varargin{7-Amatrix-Bnotthere:end});
    end
    if (nargout == 3)
        varargout{3} = 0; % flag indicates "convergence"
    end
    return
end

if isrealprob & ~issymA
    sigmar = real(sigma);
    sigmai = imag(sigma);
end

if isrealprob & issymA
    if (p <= k)
        error(['For real symmetric problems, must have number of' ...
                ' basis vectors opts.p > k'])
    end
else
    if (p <= k+1)
        error(['For nonsymmetric and complex problems, must have number of' ...
                ' basis vectors opts.p > k+1'])
    end
end

% Determine mode
if isequal(whch,'LM') & ~isequal(sigma,0)
    mode = 3;
elseif isempty(B)
    mode = 1;
else
    mode = 2;
end

if cholB
    pB = 0;
    RB = B;
    RBT = B';
end

if (mode == 3) & Amatrix % need lu(A-sigma*B)
    if issparse(A) & (isempty(B) | issparse(B))
        if isempty(B)
            AsB = A - sigma * speye(n);
        else
            if cholB
                AsB = A - sigma * RBT * RB;
            else
                AsB = A - sigma * B;
            end
        end
        perm = colmmd(AsB);
        [L,U,P] = lu(AsB(:,perm));
    else
        if isempty(B)
            AsB = A - sigma * eye(n);
        else
            if cholB
                AsB = A - sigma * RBT * RB;
            else
                AsB = A - sigma * B;
            end
        end
        [L,U,P] = lu(AsB);
    end
    dU = diag(U);
    rcondestU = double(min(abs(dU)) / max(abs(dU)));
    if (rcondestU < eps)
        if isempty(B)
            ds = sprintf(['(A-sigma*I) has small reciprocal condition' ...
                    ' estimate: %f\n'],rcondestU);
        else
            ds = sprintf(['(A-sigma*B) has small reciprocal condition' ...
                    ' estimate: %f\n'],rcondestU);
        end
        ds = [ds sprintf(['indicating that sigma is near an exact' ...
                    ' eigenvalue. The\nalgorithm may not converge unless' ...
                    ' you try a new value for sigma.\n'])];
        disp(ds)
        pause(2)
    end
end

if (mode == 2) & ~cholB % need chol(B)
    if issparse(B)
        permB = symmmd(B);
        [RB,pB] = chol(B(permB,permB));
    else
        [RB,pB] = chol(B);
    end
    if (pB == 0)
        RBT = RB';
    else
        error(Bstr)
    end
end

% Allocate outputs and ARPACK work variables
if isrealprob
    if issymA % real and symmetric
        prefix = 'ds';
        v = zeros(n,p);
        ldv = int32(size(v,1));
        ipntr = int32(zeros(15,1));
        workd = zeros(n,3);
        lworkl = p*(p+8);
        workl = zeros(lworkl,1);
        lworkl = int32(lworkl);
        d = zeros(k,1);
    else % real but not symmetric
        prefix = 'dn';
        v = zeros(n,p);
        ldv = int32(size(v,1));
        ipntr = int32(zeros(15,1));
        workd = zeros(n,3);
        lworkl = 3*p*(p+2);
        workl = zeros(lworkl,1);
        lworkl = int32(lworkl);
        workev = zeros(3*p,1);
        d = zeros(k+1,1);
        di = zeros(k+1,1);
    end
else % complex
    prefix = 'zn';
    zv = zeros(2*n*p,1);
    ldv = int32(n);
    ipntr = int32(zeros(15,1));
    workd = complex(zeros(n,3));
    zworkd = zeros(2*prod(size(workd)),1);
    lworkl = 3*p^2+5*p;
    workl = zeros(2*lworkl,1);
    lworkl = int32(lworkl);
    workev = zeros(2*2*p,1);
    zd = zeros(2*(k+1),1);
    rwork = zeros(p,1);
end

ido = int32(0); % reverse communication parameter
if isempty(B)
    bmat = 'I'; % standard eigenvalue problem
else
    bmat = 'G'; % generalized eigenvalue problem
end
nev = int32(k); % number of eigenvalues requested
ncv = int32(p); % number of Lanczos vectors
iparam = int32(zeros(11,1));
iparam([1 3 7]) = int32([1 maxit mode]);
select = int32(zeros(p,1));

cputms(1) = cputime - t0; % end timing pre-processing

iter = 0;
ariter = 0;

while (ido ~= 99)
        
    t0 = cputime; % start timing ARPACK calls **aupd
        
    if isrealprob
        arpackc( [prefix 'aupd'], ido, ...
            bmat, int32(n), whch, nev, tol, resid, ncv, ...
            v, ldv, iparam, ipntr, workd, workl, lworkl, info);
    else
        zworkd(1:2:end-1) = real(workd);
        zworkd(2:2:end) = imag(workd);
        arpackc( 'znaupd', ido, ...
            bmat, int32(n), whch, nev, tol, resid, ncv, zv, ...
            ldv, iparam, ipntr, zworkd, workl, lworkl, ...
            rwork, info );
        workd = reshape(complex(zworkd(1:2:end-1),zworkd(2:2:end)),[n,3]);
    end

    if (info < 0)
        es = sprintf('Error with ARPACK routine %saupd: info = %d',...
           prefix,double(info));
        error(es)
    end
     
    cputms(2) = cputms(2) + (cputime-t0); % end timing ARPACK calls **aupd
    t0 = cputime; % start timing MATLAB OP(X)
    
    % Compute which columns of workd ipntr references
    [row,col1] = ind2sub([n,3],double(ipntr(1)));
    if (row ~= 1)
        str = sprintf(['ipntr(1)=%d does not refer to the start of a' ...
                ' column of the %d-by-3 array workd'],double(ipntr(1)),n);
        error(str)
    end
    [row,col2] = ind2sub([n,3],double(ipntr(2)));
    if (row ~= 1)
        str = sprintf(['ipntr(2)=%d does not refer to the start of a' ...
                ' column of the %d-by-3 array workd'],double(ipntr(2)),n);
        error(str)
    end
    if ~isempty(B) & (mode == 3) & (ido == 1)
        [row,col3] = ind2sub([n,3],double(ipntr(3)));
        if (row ~= 1)
            str = sprintf(['ipntr(3)=%d does not refer to the start of a' ...
                    ' column of the %d-by-3 array workd'],double(ipntr(3)),n);
            error(str)
        end
    end
    
    if ((ido == -1) | (ido == 1))
        if Amatrix
            if (mode == 1)
                workd(:,col2) = A * workd(:,col1);
            elseif (mode == 2)
                workd(:,col1) = A * workd(:,col1);
                if issparse(B)
                    workd(permB,col2) = RB \ (RBT \workd(permB,col1));
                else
                    workd(:,col2) = RB \ (RBT \workd(:,col1));
                end
            elseif (mode == 3)
                if isempty(B)
                    if issparse(A)
                        workd(perm,col2) = U \ (L \ (P * workd(:,col1)));
                    else
                        workd(:,col2) = U \ (L \ (P * workd(:,col1)));
                    end
                else % B is not empty
                    if (ido == -1)
                        if cholB
                            workd(:,col2) = RBT * (RB * workd(:,col1));
                        else
                            workd(:,col2) = B * workd(:,col1);
                        end
                        if issparse(A) & issparse(B)
                            workd(perm,col2) = U \ (L \ (P * workd(:,col1)));
                        else
                            workd(:,col2) = U \ (L \ (P * workd(:,col1)));
                        end
                    elseif (ido == 1)
                        if issparse(A) & issparse(B)
                            workd(perm,col2) = U \ (L \ (P * workd(:,col3)));
                        else
                            workd(:,col2) = U \ (L \ (P * workd(:,col3)));
                        end
                    end
                end
            else % mode is not 1,2 or 3
                error(['Unknown mode returned from ' prefix 'aupd'])
            end
        else % A is not a matrix
            if (mode == 1)
                workd(:,col2) = feval(A,workd(:,col1), ...
                    varargin{7-Amatrix-Bnotthere:end});
            elseif (mode == 2)
                workd(:,col1) = feval(A,workd(:,col1), ...
                    varargin{7-Amatrix-Bnotthere:end});
                if issparse(B)
                    workd(permB,col2) = RB \ (RBT \workd(permB,col1));
                else
                    workd(:,col2) = RB \ (RBT \workd(:,col1));
                end
            elseif (mode == 3)
                if isempty(B)
                    workd(:,col2) = feval(A,workd(:,col1), ...
                        varargin{7-Amatrix-Bnotthere:end});
                else
                    if (ido == -1)
                        if cholB
                            workd(:,col2) = RBT * (RB * workd(:,col1));
                        else
                            workd(:,col2) = B * workd(:,col1);
                        end
                        workd(:,col2) = feval(A,workd(:,col2), ...
                            varargin{7-Amatrix-Bnotthere:end});
                    elseif (ido == 1)
                        workd(:,col2) = feval(A,workd(:,col3), ...
                            varargin{7-Amatrix-Bnotthere:end});
                    end
                end
            else % mode is not 1,2 or 3
                error(['Unknown mode returned from ' prefix 'aupd'])
            end
        end % if Amatrix
    elseif (ido == 2)
        if (mode == 2) | (mode == 3)
            if cholB
                workd(:,col2) = RBT * (RB * workd(:,col1));
            else
                workd(:,col2) = B * workd(:,col1);
            end
        else
            error(['Unknown mode returned from ' prefix 'aupd'])
        end
    elseif (ido == 3)
        % setting iparam(1) = ishift = 1 ensures this never happens
        warning(['eigs does not yet support computing the shifts in workl.' ...
                ' Setting reverse communication parameter to 99 and returning'])
        ido = int32(99);
    elseif (ido ~= 99)
        error(['Unknown value of reverse communication parameter' ...
                ' returned from ' prefix 'aupd'])      
    end
    
    cputms(3) = cputms(3) + (cputime-t0); % end timing MATLAB OP(X)

    if display
        iter = double(ipntr(15));
        if (iter > ariter) & (ido ~= 99)
            ariter = iter;
            ds = sprintf(['Iteration %d: a few Ritz values of the' ...
                    ' %d-by-%d matrix:'],iter,p,p);
            disp(ds)
            if isrealprob
                if issymA
                    dispvec = [workl(double(ipntr(6))+(0:p-1))];
                    if isequal(whch,'BE')
                        % roughly k Large eigenvalues and k Small eigenvalues
                        disp(dispvec(end-2*k+1:end))
                    else
                        % k eigenvalues
                        disp(dispvec(end-k+1:end))
                    end
                else
                    dispvec = [complex(workl(double(ipntr(6))+(0:p-1)), ...
                            workl(double(ipntr(7))+(0:p-1)))];
                    % k+1 eigenvalues (keep complex conjugate pairs together)
                    disp(dispvec(end-k:end))
                end
            else
                dispvec = [complex(workl(2*double(ipntr(6))-1+(0:2:2*(p-1))), ...
                        workl(2*double(ipntr(6))+(0:2:2*(p-1))))];
                disp(dispvec(end-k+1:end))
            end
        end
    end
    
end % while (ido ~= 99)

t0 = cputime; % start timing post-processing

flag = 0;
if (info < 0)
    es = sprintf('Error with ARPACK routine %saupd: info = %d',prefix,double(info));
    error(es)
else
    if (nargout >= 2)
        rvec = int32(1); % compute eigenvectors
    else
        rvec = int32(0); % do not compute eigenvectors
    end
    
    if isrealprob
        if issymA
            arpackc( 'dseupd', rvec, 'A', select, ...
                d, v, ldv, sigma, ...
                bmat, int32(n), whch, nev, tol, resid, ncv, ...
                v, ldv, iparam, ipntr, workd, workl, lworkl, info );
            if isequal(whch,'LM') | isequal(whch,'LA')
                d = flipud(d);
                if (rvec == 1)
                    v(:,1:k) = v(:,k:-1:1);
                end
            end
            if ((isequal(whch,'SM') | isequal(whch,'SA')) & (rvec == 0))
                d = flipud(d);
            end
        else
            arpackc( 'dneupd', rvec, 'A', select, ...
                d, di, v, ldv, sigmar, sigmai, workev, ...
                bmat, int32(n), whch, nev, tol, resid, ncv, ...
                v, ldv, iparam, ipntr, workd, workl, lworkl, info );
            d = complex(d,di);
            if rvec
                d(k+1) = [];
            else
                zind = find(d == 0);
                if isempty(zind)
                    d = d(k+1:-1:2);
                else
                    d(max(zind)) = [];
                    d = flipud(d);
                end
            end
        end
    else
        zsigma = [real(sigma); imag(sigma)];
        arpackc( 'zneupd', rvec, 'A', select, ...
            zd, zv, ldv, zsigma, workev, ...
            bmat, int32(n), whch, nev, tol, resid, ncv, zv, ...
            ldv, iparam, ipntr, zworkd, workl, lworkl, ...
            rwork, info );
        if issymA
            d = zd(1:2:end-1);
        else
            d = complex(zd(1:2:end-1),zd(2:2:end));
        end
        v = reshape(complex(zv(1:2:end-1),zv(2:2:end)),[n p]);
    end
    
    if (info ~= 0)
        es = ['Error with ARPACK routine ' prefix 'eupd: '];
        switch double(info)
            case 2
            ss = sum(select);
            if (ss < k)
            es = [es ...
                    '  The logical variable select was only set with ' int2str(ss) ...
                    ' 1''s instead of nconv=' int2str(double(iparam(5))) ...
                    ' (k=' int2str(k) ').' ...
                    ' Please contact the ARPACK authors at arpack@caam.rice.edu'];
            else
            es = [es ...
                    'The LAPACK reordering routine ' prefix(1) ...
                    'trsen did not return all ' int2str(k) ' eigenvalues.']
            end
            case 1
            es = [es ...
                    'The Schur form could not be reordered by the LAPACK routine ' ...
                    prefix(1) 'trsen.' ...
                    ' Please contact the ARPACK authors at arpack@caam.rice.edu'];
            case -14
            es = [es prefix ...
                    'aupd did not find any eigenvalues to sufficient accuracy'];
            otherwise
            es = [es sprintf('info = %d',double(info))];
        end
        error(es)
    else
        nconv = double(iparam(5));
        if (nconv == 0)
            if (nargout < 3)
                ws = sprintf(['None of the %d requested eigenvalues' ...
                        ' converged'],k);
                warning(ws)
            else
                flag = 1;
            end
        elseif (nconv < k)
            if (nargout < 3)
                ws = sprintf(['Only %d of the %d requested eigenvalues' ...
                        ' converged'],nconv,k);
                warning(ws)
            else
                flag = 1;
            end
        end
    end % if (info ~= 0)
end % if (info < 0)

if (issymA) | (~isrealprob)
    if (nargout <= 1)
        if isrealprob
            varargout{1} = d;
        else
            varargout{1} = d(k:-1:1,1);
        end
    else
        varargout{1} = v(:,1:k);
        varargout{2} = diag(d(1:k,1));
        if (nargout >= 3)
            varargout{3} = flag;
        end
    end
else
    if (nargout <= 1)
        varargout{1} = d;
    else
        cplxd = find(di ~= 0);
        % complex conjugate pairs of eigenvalues occur together
        cplxd = cplxd(1:2:end);
        v(:,[cplxd cplxd+1]) = [complex(v(:,cplxd),v(:,cplxd+1)) ...
                complex(v(:,cplxd),-v(:,cplxd+1))];
        varargout{1} = v(:,1:k);
        varargout{2} = diag(d);
        if (nargout >= 3)
            varargout{3} = flag;
        end
    end
end

cputms(4) = cputime-t0; % end timing post-processing

cputms(5) = sum(cputms(1:4)); % total time

if (display == 2)
    if (mode == 1)
        innerstr = sprintf(['Compute A*X:' ...
                '                               %f\n'],cputms(3));
    elseif (mode == 2)
        innerstr = sprintf(['Compute A*X and solve B*X=Y for X:' ...
                '         %f\n'],cputms(3));
    elseif (mode == 3)
        if isempty(B)
            innerstr = sprintf(['Solve (A-SIGMA*I)*X=Y for X:' ...
                    '               %f\n'],cputms(3));
        else
            innerstr = sprintf(['Solve (A-SIGMA*B)*X=B*Y for X:' ...
                    '             %f\n'],cputms(3));
        end
    end
    if ((mode == 3) & (Amatrix))
        if isempty(B)
            prepstr = sprintf(['Pre-processing, including lu(A-sigma*I):' ...
                    '   %f\n'],cputms(1));
        else
            prepstr = sprintf(['Pre-processing, including lu(A-sigma*B):' ...
                    '   %f\n'],cputms(1));
        end
    elseif ((mode == 2) & (~cholB))
        prepstr = sprintf(['Pre-processing, including chol(B):' ...
                '         %f\n'],cputms(1));
    else
        prepstr = sprintf(['Pre-processing:' ...
                '                            %f\n'],cputms(1));
    end
    sstr = sprintf(['***********CPU Timing Results in seconds***********']);
    ds = sprintf(['\n' sstr '\n' ...
            prepstr ...
            'ARPACK''s %saupd:                           %f\n' ...
            innerstr ...
            'Post-processing with ARPACK''s %seupd:      %f\n' ...
            '***************************************************\n' ...
            'Total:                                     %f\n' ...
            sstr '\n'], ...
        prefix,cputms(2),prefix,cputms(4),cputms(5));
    disp(ds)
end

