# R code for the paper "Invoice level forecasting with discrete survival
# methods for effective forecasting of account receivables in supply chain" by
# Sanjay Saini, Giuseppe Manai, Willem van den Boom, Maria De Iorio and Fang
# Qian

# Journal: Discover Analytics

# Corresponding author: Willem van den Boom, National University of Singapore
# Email address: vandenboom@nus.edu.sg



## ----------------------------------------------------------------------------
# Install the required packages.
for (package_name in c(
  "discSurv", "dplyr", "forecast", "ggplot2", "lme4", "merTools", "pracma",
  "pROC", "survival", "tsibble", "VGAM"
)) {
  if(!package_name %in% rownames(installed.packages())) install.packages(
    pkgs = package_name, repos = "https://cloud.r-project.org",
    dependencies = TRUE
  )
}


# Get details on the R environment.
# Output from the machine used for the results in the paper is included as
# comments.
installed.packages()[, c("Package", "Version")]
#               Package         Version     
# abind         "abind"         "1.4-5"     
# anytime       "anytime"       "0.3.9"     
# arm           "arm"           "1.13-1"    
# backports     "backports"     "1.4.1"     
# base64enc     "base64enc"     "0.1-3"     
# BH            "BH"            "1.84.0-0"  
# blme          "blme"          "1.0-5"     
# brio          "brio"          "1.1.4"     
# broom         "broom"         "1.0.5"     
# broom.mixed   "broom.mixed"   "0.2.9.4"   
# bslib         "bslib"         "0.6.1"     
# cachem        "cachem"        "1.0.8"     
# callr         "callr"         "3.7.5"     
# car           "car"           "3.1-2"     
# carData       "carData"       "3.0-5"     
# cli           "cli"           "3.6.2"     
# coda          "coda"          "0.19-4.1"  
# colorspace    "colorspace"    "2.1-0"     
# commonmark    "commonmark"    "1.9.1"     
# corrplot      "corrplot"      "0.92"      
# cowplot       "cowplot"       "1.1.3"     
# cpp11         "cpp11"         "0.4.7"     
# crayon        "crayon"        "1.5.2"     
# curl          "curl"          "5.2.1"     
# data.table    "data.table"    "1.15.2"    
# desc          "desc"          "1.4.3"     
# diffobj       "diffobj"       "0.3.5"     
# digest        "digest"        "0.6.35"    
# discSurv      "discSurv"      "2.0.0"     
# dplyr         "dplyr"         "1.1.4"     
# ellipsis      "ellipsis"      "0.3.2"     
# evaluate      "evaluate"      "0.23"      
# fansi         "fansi"         "1.0.6"     
# farver        "farver"        "2.1.1"     
# fastmap       "fastmap"       "1.1.1"     
# fontawesome   "fontawesome"   "0.5.2"     
# forcats       "forcats"       "1.0.0"     
# foreach       "foreach"       "1.5.2"     
# forecast      "forecast"      "8.22.0"    
# fracdiff      "fracdiff"      "1.5-3"     
# fs            "fs"            "1.6.3"     
# functional    "functional"    "0.6"       
# furrr         "furrr"         "0.3.1"     
# future        "future"        "1.33.1"    
# geepack       "geepack"       "1.3.10"    
# generics      "generics"      "0.1.3"     
# ggplot2       "ggplot2"       "3.5.0"     
# ggpubr        "ggpubr"        "0.6.0"     
# ggrepel       "ggrepel"       "0.9.5"     
# ggsci         "ggsci"         "3.0.1"     
# ggsignif      "ggsignif"      "0.6.4"     
# globals       "globals"       "0.16.3"    
# glue          "glue"          "1.7.0"     
# gridExtra     "gridExtra"     "2.3"       
# gtable        "gtable"        "0.3.4"     
# highr         "highr"         "0.10"      
# htmltools     "htmltools"     "0.5.7"     
# httpuv        "httpuv"        "1.6.14"    
# isoband       "isoband"       "0.2.7"     
# iterators     "iterators"     "1.0.14"    
# jquerylib     "jquerylib"     "0.1.4"     
# jsonlite      "jsonlite"      "1.8.8"     
# knitr         "knitr"         "1.45"      
# labeling      "labeling"      "0.4.3"     
# later         "later"         "1.3.2"     
# lifecycle     "lifecycle"     "1.0.4"     
# listenv       "listenv"       "0.9.1"     
# lme4          "lme4"          "1.1-35.1"  
# lmtest        "lmtest"        "0.9-40"    
# lubridate     "lubridate"     "1.9.3"     
# magrittr      "magrittr"      "2.0.3"     
# MatrixModels  "MatrixModels"  "0.5-3"     
# memoise       "memoise"       "2.0.1"     
# merTools      "merTools"      "0.6.2"     
# mime          "mime"          "0.12"      
# minqa         "minqa"         "1.2.6"     
# munsell       "munsell"       "0.5.0"     
# mvnfast       "mvnfast"       "0.2.8"     
# mvtnorm       "mvtnorm"       "1.2-4"     
# nloptr        "nloptr"        "2.0.3"     
# numDeriv      "numDeriv"      "2016.8-1.1"
# parallelly    "parallelly"    "1.37.1"    
# pbkrtest      "pbkrtest"      "0.5.2"     
# pillar        "pillar"        "1.9.0"     
# pkgbuild      "pkgbuild"      "1.4.3"     
# pkgconfig     "pkgconfig"     "2.0.3"     
# pkgload       "pkgload"       "1.3.4"     
# plyr          "plyr"          "1.8.9"     
# polynom       "polynom"       "1.4-1"     
# pracma        "pracma"        "2.4.4"     
# praise        "praise"        "1.0.0"     
# pROC          "pROC"          "1.18.5"    
# processx      "processx"      "3.8.3"     
# promises      "promises"      "1.2.1"     
# ps            "ps"            "1.7.6"     
# purrr         "purrr"         "1.0.2"     
# quadprog      "quadprog"      "1.5-8"     
# quantmod      "quantmod"      "0.4.26"    
# quantreg      "quantreg"      "5.97"      
# R6            "R6"            "2.5.1"     
# ranger        "ranger"        "0.16.0"    
# rappdirs      "rappdirs"      "0.3.3"     
# rbibutils     "rbibutils"     "2.2.16"    
# RColorBrewer  "RColorBrewer"  "1.1-3"     
# Rcpp          "Rcpp"          "1.0.12"    
# RcppArmadillo "RcppArmadillo" "0.12.8.1.0"
# RcppEigen     "RcppEigen"     "0.3.4.0.0" 
# Rdpack        "Rdpack"        "2.6"       
# rematch2      "rematch2"      "2.1.2"     
# renv          "renv"          "1.0.5"     
# rlang         "rlang"         "1.1.3"     
# rmarkdown     "rmarkdown"     "2.26"      
# rprojroot     "rprojroot"     "2.0.4"     
# rstatix       "rstatix"       "0.7.2"     
# sass          "sass"          "0.4.8"     
# scales        "scales"        "1.3.0"     
# shiny         "shiny"         "1.8.0"     
# sourcetools   "sourcetools"   "0.1.7-1"   
# SparseM       "SparseM"       "1.81"      
# stringi       "stringi"       "1.8.3"     
# stringr       "stringr"       "1.5.1"     
# testthat      "testthat"      "3.2.1"     
# tibble        "tibble"        "3.2.1"     
# tidyr         "tidyr"         "1.3.1"     
# tidyselect    "tidyselect"    "1.2.1"     
# timechange    "timechange"    "0.3.0"     
# timeDate      "timeDate"      "4032.109"  
# tinytex       "tinytex"       "0.49"      
# treeClust     "treeClust"     "1.1-7"     
# tseries       "tseries"       "0.10-55"   
# tsibble       "tsibble"       "1.1.4"     
# TTR           "TTR"           "0.24.4"    
# urca          "urca"          "1.3-3"     
# utf8          "utf8"          "1.2.4"     
# vctrs         "vctrs"         "0.6.5"     
# VGAM          "VGAM"          "1.1-10"    
# viridisLite   "viridisLite"   "0.4.2"     
# waldo         "waldo"         "0.5.2"     
# withr         "withr"         "3.0.0"     
# xfun          "xfun"          "0.42"      
# xtable        "xtable"        "1.8-4"     
# xts           "xts"           "0.13.2"    
# yaml          "yaml"          "2.3.8"     
# zoo           "zoo"           "1.8-12"    
# base          "base"          "4.3.2"     
# boot          "boot"          "1.3-28"    
# class         "class"         "7.3-22"    
# cluster       "cluster"       "2.1.4"     
# codetools     "codetools"     "0.2-19"    
# compiler      "compiler"      "4.3.2"     
# datasets      "datasets"      "4.3.2"     
# foreign       "foreign"       "0.8-85"    
# graphics      "graphics"      "4.3.2"     
# grDevices     "grDevices"     "4.3.2"     
# grid          "grid"          "4.3.2"     
# KernSmooth    "KernSmooth"    "2.23-22"   
# lattice       "lattice"       "0.21-9"    
# MASS          "MASS"          "7.3-60"    
# Matrix        "Matrix"        "1.6-1.1"   
# methods       "methods"       "4.3.2"     
# mgcv          "mgcv"          "1.9-0"     
# nlme          "nlme"          "3.1-163"   
# nnet          "nnet"          "7.3-19"    
# parallel      "parallel"      "4.3.2"     
# rpart         "rpart"         "4.1.21"    
# spatial       "spatial"       "7.3-17"    
# splines       "splines"       "4.3.2"     
# stats         "stats"         "4.3.2"     
# stats4        "stats4"        "4.3.2"     
# survival      "survival"      "3.5-7"     
# tcltk         "tcltk"         "4.3.2"     
# tools         "tools"         "4.3.2"     
# utils         "utils"         "4.3.2"     

sessionInfo()
# R version 4.3.2 (2023-10-31)
# Platform: x86_64-pc-linux-gnu (64-bit)
# Running under: Ubuntu 22.04.3 LTS

# Matrix products: default
# BLAS:   /usr/lib/x86_64-linux-gnu/blas/libblas.so.3.10.0 
# LAPACK: /usr/lib/x86_64-linux-gnu/lapack/liblapack.so.3.10.0

# locale:
#  [1] LC_CTYPE=C.UTF-8       LC_NUMERIC=C           LC_TIME=C.UTF-8       
#  [4] LC_COLLATE=C.UTF-8     LC_MONETARY=C.UTF-8    LC_MESSAGES=C.UTF-8   
#  [7] LC_PAPER=C.UTF-8       LC_NAME=C              LC_ADDRESS=C          
# [10] LC_TELEPHONE=C         LC_MEASUREMENT=C.UTF-8 LC_IDENTIFICATION=C   

# time zone: Asia/Singapore
# tzcode source: system (glibc)

# attached base packages:
# [1] stats     graphics  grDevices datasets  utils     methods   base     

# loaded via a namespace (and not attached):
# [1] compiler_4.3.2 tools_4.3.2    renv_1.0.5    


## ----------------------------------------------------------------------------
library(dplyr)
library(ggplot2)
library(lme4)
library(tsibble)
library(VGAM)


## ----------------------------------------------------------------------------
# Indicate which data set is being analyzed.
# Change the following to "I" or "II" for Data I and Data II, respectively.
dataset <- "I"


## ----------------------------------------------------------------------------
# The following line of code loads the data as an R data frame.
# See the `summary` output below for how the data frame is structured.
AR_data <- readRDS(file = paste0("data_", dataset, ".rds"))
summary(AR_data)

# Output for Data I:
 #   customer         customer_type          amount        quarter  
 # Length:9932        Length:9932        Min.   :   11.0   Q1:3210  
 # Class :character   Class :character   1st Qu.:  232.8   Q2:2761  
 # Mode  :character   Mode  :character   Median :  460.0   Q3:2351  
 #                                       Mean   :  731.3   Q4:1610  
 #                                       3rd Qu.:  934.0            
 #                                       Max.   :17446.0            
 #   issue_date            due_date           closed_date        
 # Min.   :2018-02-01   Min.   :2018-03-03   Min.   :2018-02-05  
 # 1st Qu.:2018-06-25   1st Qu.:2018-07-25   1st Qu.:2018-08-13  
 # Median :2018-12-07   Median :2019-01-06   Median :2019-02-25  
 # Mean   :2019-01-28   Mean   :2019-02-27   Mean   :2019-03-19  
 # 3rd Qu.:2019-08-19   3rd Qu.:2019-09-18   3rd Qu.:2019-09-30  
 # Max.   :2020-07-27   Max.   :2020-08-26   Max.   :2020-07-31  


# Output for Data II:
 #   customer             amount         quarter     issue_date        
 # Length:35192       Min.   :     0.0   1:10645   Min.   :2009-01-07  
 # Class :character   1st Qu.:   388.2   2:10561   1st Qu.:2010-10-13  
 # Mode  :character   Median :  1056.0   3: 9801   Median :2012-10-30  
 #                    Mean   :  3038.5   4: 4185   Mean   :2013-02-12  
 #                    3rd Qu.:  2816.1             3rd Qu.:2015-05-29  
 #                    Max.   :509300.0             Max.   :2017-09-20  
 #    due_date           closed_date              tax        
 # Min.   :2009-03-02   Min.   :2009-01-16   Min.   :0.0000  
 # 1st Qu.:2010-11-30   1st Qu.:2010-11-30   1st Qu.:1.0000  
 # Median :2012-11-30   Median :2012-12-14   Median :1.0000  
 # Mean   :2013-03-27   Mean   :2013-04-02   Mean   :0.9877  
 # 3rd Qu.:2015-06-30   3rd Qu.:2015-07-24   3rd Qu.:1.0000  
 # Max.   :2017-10-30   Max.   :2017-09-26   Max.   :1.0000  


## ----------------------------------------------------------------------------
if (dataset == "II") AR_data$payment_term_days <- as.integer(difftime(
  time1 = AR_data$due_date, time2 = AR_data$issue_date, units = "days"
))

AR_data$log_amount <- log(AR_data$amount + 1)

AR_data$time_to_payment <- as.numeric(difftime(
  time1 = AR_data$closed_date, time2 = AR_data$issue_date, units = "days"
))

# Transform the time-to-event data into long format
AR_data$eventColumn <- 1L

AR_data_long <- discSurv::dataLong(
  dataShort = AR_data, timeColumn = "time_to_payment",
  eventColumn = "eventColumn"
)

tau <-  max(AR_data_long$time_to_payment)
n <- nrow(AR_data)


## ----------------------------------------------------------------------------
# Fit the random effects discrete survival model
formula <- switch(
  dataset,
  "I"  = y ~ bs(timeInt, 3) + (1 | customer) + log_amount * bs(timeInt, 3) +
    quarter + customer_type,
  "II" = y ~ bs(timeInt, 3) + (1 | customer) + log_amount * bs(timeInt, 3) +
    quarter + payment_term_days + tax
)

print("Fitting model...")

model_fit <-  glmer(
  formula = formula, data = AR_data_long, family = binomial(link = "cloglog")
)

summary(model_fit)


## ----------------------------------------------------------------------------
confint(object = model_fit, parm = "beta_", method = "Wald")


## ----------------------------------------------------------------------------
# Predict time to payment using the model fit
AR_data_long_all <- data.frame(
  timeInt = rep(1:tau, n), customer = rep(AR_data$customer, each = tau),
  issue_date = rep(AR_data$issue_date, each = tau),
  quarter = rep(AR_data$quarter, each = tau),
  log_amount = rep(AR_data$log_amount, each = tau)
)

if (dataset == "I") {
  AR_data_long_all$customer_type <- rep(AR_data$customer_type, each = tau)
} else {
  AR_data_long_all$payment_term_days <-
    rep(AR_data$payment_term_days, each = tau)
  
  AR_data_long_all$tax <- rep(AR_data$tax, each = tau)
}

AR_data_long_all$hazard <- predict(
  model_fit, newdata = AR_data_long_all, type = "response"
)

prob_payment <- apply(
  matrix(AR_data_long_all$hazard, tau, n), 2L,
  function (x) x * c(1, head(cumprod(1 - x), -1))
)

AR_data$predicted_time <- round(
  apply(prob_payment, 2, function (x) sum((1:tau) * x))
)


## ----------------------------------------------------------------------------
# For comparison, fit a Cox proportional hazards model.
formula <- switch(
  dataset,
  "I" = survival::Surv(time_to_payment) ~ log_amount + quarter + customer_type,
  "II" = survival::Surv(time_to_payment) ~
    log_amount + quarter + payment_term_days + tax
)

model_fit_cox <-  survival::coxph(formula, AR_data)

# Compute the corresponding predicted/mean time to payment for each invoice.
surv_fit <- survival::survfit(
  formula = model_fit_cox, newdata = AR_data, se.fit = FALSE
)

AR_data$predicted_time_Cox <- NA_real_

for (j in 1:n) AR_data$predicted_time_Cox[j] <- round(
  pracma::trapz(x = surv_fit$time, y = surv_fit$surv[, j])
)


## ----------------------------------------------------------------------------
# We now turn towards estimating the survival function for six companies.
# We only consider companies with at least 10 invoices.
id_table <- table(AR_data$customer)
id_all <- names(id_table[id_table >=10])

median_time <- aggregate(
  x = time_to_payment ~ customer,
  data = AR_data[AR_data$customer %in% id_all, ], FUN = median
)

id_min <- median_time$customer[which.min(median_time$time_to_payment)]
id_max <- median_time$customer[which.max(median_time$time_to_payment)]
set.seed(if (dataset == "I") 3L else 1L)

id_sub <- c(
  sample(x = id_all[!(id_all %in% c(id_max, id_min))], size = 4L), id_max,
  id_min
)

pdf(file = paste0("surv_func_", dataset, ".pdf"), width = 9, height = 6)
par(mfcol = c(2,3), cex = 1)

for (i in 1:length(id_sub)){
  n_id <- sum(AR_data$customer == id_sub[i])
  
  # Kaplan-Meier estimate
  KM_est <- discSurv::lifeTable(
    dataShort = AR_data[AR_data$customer == id_sub[i], ],
    timeColumn = "time_to_payment", eventColumn = "eventColumn"
  )$Output[,  "S"]
  
  # Estimate the survival function with confidence bands
  prediction_interval <- merTools::predictInterval(
    model_fit, AR_data_long_all[AR_data_long_all$customer == id_sub[i], ],
    level = 0.95, n.sims = 1000L, type = "probability",
    include.resid.var = FALSE, fix.intercept.variance = TRUE
  )
  
  surv_est <- apply(apply(
    matrix(prediction_interval$fit, tau, n_id), 2,  function(x) cumprod(1 - x)
  ), 1, mean)
  
  surv_upr <- apply(apply(
    matrix(prediction_interval$upr, tau, n_id), 2,  function(x) cumprod(1 - x)
  ), 1, mean)
  
  surv_lwr <- apply(apply(
    matrix(prediction_interval$lwr, tau, n_id), 2,  function(x) cumprod(1 - x)
  ), 1, mean)
  
  median_empirical <- min(which(KM_est <= 0.5))
  median_fit <- min(which(surv_est <= 0.5))
  
  print(paste(
    "Median time", c("model fit:", "empirical:"),
    c(median_fit, median_empirical)
  ))
  
  plot(
    surv_est, type = "l",
    xlab = expression(paste("Time ", italic(t), " (days)")),
    ylab = expression(italic(S)(italic(t))), col = "blue", xaxs = "i",
    yaxs = "i", ylim = 0:1, xlim = c(0, tau + 1), main = paste("Company", i)
  )
  
  polygon(
    x = c(1:(tau + 1L), rev(1:(tau + 1L))),
    y = c(surv_lwr, 0, 0, rev(surv_upr)), col = "skyblue", border = NA
  )
  
  lines(c(surv_est, 0), col = "blue", lwd = 2)
  lines(KM_est, lty = "dashed", col="chocolate", lwd = 2)
  segments(median_fit, -2, median_fit, 0.5, col = "blue", lwd = 0.5)
  
  segments(
    median_empirical, -2, median_empirical, 0.5, col = "chocolate", lwd = 0.5
  )
  
  segments(-10, 0.5, max(median_fit, median_empirical), 0.5, lwd = 0.5)
  points(t(c(median_fit, 0.5)), cex = 1, col = "blue", pch = 16)
  points(t(c(median_empirical, 0.5)), cex = 1, col = "chocolate", pch = 16)

}

dev.off()


## ----------------------------------------------------------------------------
# Compute intervals for amount prediction through Monte Carlo (MC) simulation.
dates <- seq(
  from = min(AR_data$issue_date), to = max(AR_data$issue_date) + tau,
  by = "days"
)

n_dates <- length(dates)
n_MC_samples <- 1e5L
MC_amount_day <- matrix(data = 0, nrow = n_MC_samples, ncol = n_dates)
ind_mat <- matrix(data = 1:n_MC_samples, nrow = n_MC_samples, ncol = 2L)
set.seed(1L)
print("Running Monte Carlo simulation...")
pb <- txtProgressBar(max = n, style = 3L)

for (j in 1:n) {
  ind_mat[, 2] <- match(sample.int(
    n = tau, size = n_MC_samples, replace = TRUE, prob = prob_payment[, j]
  ), as.integer(dates - AR_data$issue_date[j]))
  
  MC_amount_day[ind_mat] <- MC_amount_day[ind_mat] + AR_data$amount[j]
  setTxtProgressBar(pb, j)
}

close(pb)


## ----------------------------------------------------------------------------
cols <- c(
  '#2ca02c', '#d62728', '#ff7f0e', '#1f77b4', '#9467bd', '#8c564b', '#e377c2'
)

# Generate the daily plot
AR_data$predicted_date <- AR_data$issue_date + AR_data$predicted_time
AR_data$predicted_date_Cox <- AR_data$issue_date + AR_data$predicted_time_Cox

daily_actual <- aggregate(
  amount ~ closed_date, data = AR_data, FUN = sum
)

daily_expected <- aggregate(
  amount ~ due_date, data = AR_data, FUN = sum
)

daily_predicted_Cox <- aggregate(
  amount ~ predicted_date_Cox, data = AR_data, FUN = sum
)

daily_predicted <- aggregate(
  amount ~ predicted_date, data = AR_data, FUN = sum
)

names(daily_actual)[1] <- "date"
names(daily_expected)[1] <- "date"
names(daily_predicted_Cox)[1] <- "date"
names(daily_predicted)[1] <- "date"

daily <- rbind(
  daily_actual, daily_expected, daily_predicted_Cox, daily_predicted
)

daily$group <- rep(
  c("Observed date", "Due date", "Predicted date (Cox)", "Predicted date"),
  c(
    nrow(daily_actual), nrow(daily_expected), nrow(daily_predicted_Cox),
    nrow(daily_predicted)
  )
)


if (dataset == "II") {
  # Exclude months for which only limited data are available.
  daily <- daily[daily$date >= "2009-03-01" & daily$date < "2017-09-01", ]
}


# Add missing days.
for (day in seq(
  from = min(daily$date), to = max(daily$date) + 6L, by = "days"
)) for (group in unique(daily$group)) {
  day <- as.Date(day)
  
  if (!(day %in% daily$date[daily$group == group])) {
    ind <- nrow(daily) + 1L
    daily[ind, 1] <- day
    daily[ind, 2] <- 0
    daily[ind, 3] <- group
  }
}

# Specify the order of the lines.
daily$group <- factor(daily$group, levels = c(
  "Observed date", "Due date", "Predicted date (Cox)", "Predicted date",
  "Moving average"
))

levels(daily$group) <- c(
  "Actual amount", "Expected amount", "Predicted amount (Cox)",
  "Predicted amount (discrete)", "Moving average"
)

daily$amount_K <- daily$amount / 1000  # Amounts in thousand USD


plot_subset <- function (daily_subset, title) ggplot() +
  geom_line(
    data=daily_subset, aes(x=date, y=amount_K, color= group, group = group)
  ) + geom_point(
    data=daily_subset,
    aes(x=date, y=amount_K, col= group, group = group, pch = group)
  ) + labs(x = "Payment day", y = "Amount (thousand $)") + theme_classic() +
  scale_color_manual(values = cols) + ggtitle(title) +
  theme(text = element_text(size = 17), legend.title=element_blank()) +
  ylim(0, 82) + scale_x_yearmonth(date_breaks = "1 month")


if (dataset == "I") {
  pdf(file = "daily_I.pdf", width = 12, height = 6)
  
  print(ggpubr::ggarrange(
    plot_subset(
      daily[daily$date >= "2018-03-01" & daily$date < "2018-09-01", ],
      title = "Pre-COVID"
    ),
    plot_subset(
      daily[daily$date >= "2020-01-01" & daily$date < "2020-07-01", ],
      title = "Post-COVID"
    ), nrow = 2L, ncol = 1L, common.legend = TRUE, legend = "top"
  ))
  
  dev.off()
}


## ----------------------------------------------------------------------------
get_MASE <- function (predicted, actual) {
  # Compute the mean absolute scaled error
  return (
    mean(abs(predicted - actual)) / mean(abs(actual[-1] - head(actual, -1L)))
  )
}

compute_table <- function (daily, compare_group) {
  dates <- unique(daily$date)
  n_dates <- length(dates)
  
  # Difference of the absolute residual for expected versus predicted
  diff_abs_resid <- numeric(n_dates)
  
  for (i in 1:n_dates) {
    actual_amount <-
      daily$amount_K[daily$date == dates[i] & daily$group == "Actual amount"]
    
    compare_amount <-
      daily$amount_K[daily$date == dates[i] & daily$group == compare_group]
    
    predicted_amount <- daily$amount_K[
      daily$date == dates[i] & daily$group == "Predicted amount (discrete)"
    ]
    
    diff_abs_resid[i] <- abs(actual_amount - compare_amount) -
        abs(actual_amount - predicted_amount)
  }
  
  print(paste0("How often is the prediction closer than ", compare_group, "?"))
  print(paste(sum(diff_abs_resid > 0) / n_dates, "proportion of days."))
  amount_better <- sum(diff_abs_resid)
  
  print(paste(
    "The prediction is", amount_better, "closer in aggregate which is",
    amount_better / sum(daily$amount_K[daily$group == "Actual amount"]),
    "of the total amount received."
  ))
  
  print("MASE")
  ordered <- daily[order(daily$date), ]
  actual <- ordered$amount_K[ordered$group == "Actual amount"]
  
  for (group in c("Predicted amount (discrete)", compare_group)) print(paste(
    group, ":", get_MASE(ordered$amount_K[ordered$group == group], actual)
  ))
}

compute_table(daily, "Expected amount")
compute_table(daily, "Predicted amount (Cox)")


## ----------------------------------------------------------------------------
daily$month <- yearmonth(daily$date)


# Compute moving average and other forecasts at a daily resolution
get_forecast <- function (method) {
  res <- daily[daily$group == "Actual amount", ]
  res$group <- method
  res <- res[order(res$date), ]
  
  res$amount <- forecast::auto.arima(
    y = res$amount, max.p = 3, max.q = 30
  )$fitted
  
  forecast_f <- switch(method, "Moving average" = function (y) {
      return (forecast::auto.arima(y = y, max.p = 3, max.q = 30))
    }, "Theta method" = forecast::thetaf, "ETS" = forecast::ets
  )
  
  res$amount <- forecast_f(res$amount)$fitted
  return (res)
}


monthly <- aggregate(amount ~ group + month, rbind(
  daily, get_forecast("Moving average"), get_forecast("Theta method"),
  get_forecast("ETS")
), FUN = sum)

# Data frame to store the monthly prediction interval
monthly_ul <- data.frame(
  month = unique(yearmonth(dates)), low = NA_real_, high = NA_real_
)

date2month_vec <- match(yearmonth(dates), monthly_ul$month)

for (month_ind in 1:nrow(monthly_ul)) {
  monthly_ul[month_ind, c("low", "upper")] <- range(rowSums(
    MC_amount_day[, which(date2month_vec == month_ind), drop = FALSE]
  ))
}


compute_table <- function (monthly, compare_group) {
  months <- unique(monthly$month)
  n_months <- length(months)
  
  # Difference of the absolute residual for expected versus predicted
  diff_abs_resid <- numeric(n_months)
  
  for (i in 1:n_months) {
    actual_amount <- monthly$amount_M[
      monthly$month == months[i] & monthly$group == "Actual amount"
    ]
    
    compare_amount <- monthly$amount_M[
      monthly$month == months[i] & monthly$group == compare_group
    ]
    
    predicted_amount <- monthly$amount_M[
      monthly$month == months[i] &
        monthly$group == "Predicted amount (discrete)"
    ]
    
    diff_abs_resid[i] <- abs(actual_amount - compare_amount) -
        abs(actual_amount - predicted_amount)
  }
  
  print(paste0("How often is the prediction closer than ", compare_group, "?"))
  print(paste(sum(diff_abs_resid > 0) / n_months, "proportion of months"))
  amount_better <- sum(diff_abs_resid)
  
  print(paste(
    "The prediction is", amount_better, "closer in aggregate which is",
    amount_better / sum(monthly$amount_M[monthly$group == "Actual amount"]),
    "of the total amount received."
  ))
  
  print("MASE")
  ordered <- monthly[order(monthly$month), ]
  actual <- ordered$amount_M[ordered$group == "Actual amount"]
  
  for (group in c("Predicted amount (discrete)", compare_group)) print(paste(
    group, ":", get_MASE(ordered$amount_M[ordered$group == group], actual)
  ))
}


# Only keep March '18 through June '20
del_months <- yearmonth(c("2018 Feb", "2020 Jul", "2020 Aug", "2020 Sep"))
monthly <- monthly[!(monthly$month %in% del_months), ]
monthly_ul <- monthly_ul[monthly_ul$month %in% monthly$month, ]

# Ensure that the range includes the predicted amounts
for (month_ind in 1:nrow(monthly_ul)) {
  predicted_amount <- monthly$amount[
    monthly$month == monthly_ul$month[month_ind] &
      monthly$group == "Predicted amount (discrete)"
  ]
  
  monthly_ul[month_ind, c("low", "upper")] <- c(
    min(predicted_amount, monthly_ul$low[month_ind]),
    max(predicted_amount, monthly_ul$upper[month_ind])
  )
}

scale_factor <- 1e6  # To write y axis in millions
monthly$amount_M <- monthly$amount / scale_factor

compute_table(monthly, "Expected amount")
compute_table(monthly, "Predicted amount (Cox)")

pdf(file = paste0("monthly_", dataset, ".pdf"), width = 12, height = 4)

ggplot() + geom_ribbon(
  data = monthly_ul,
  aes(ymin = low / scale_factor, ymax = upper / scale_factor, x = month),
  alpha= 0.3, linetype=0,
  fill = cols[levels(monthly$group) == "Predicted amount (discrete)"]
) + geom_line(
  data=monthly, aes(x=month, y=amount_M, color= group, group = group)
) + geom_point(
  data=monthly, aes(x=month, y=amount_M, col= group, group = group, pch = group)
)  + labs(x = "Payment month", y = "Amount (million $)") + theme_classic() +
  scale_color_manual(values = cols) + theme(
    text = element_text(size = 17), legend.title = element_blank(),
    plot.margin = margin(r = 20, l = 15), legend.position = "top"
  )

dev.off()


## ----------------------------------------------------------------------------
# Comparison with classification (logistic regression)
AR_data$payment_term_days <- as.numeric(difftime(
  time1 = AR_data$due_date, time2 = AR_data$issue_date, units = "days"
))

AR_data$on_time <- AR_data$time_to_payment <= AR_data$payment_term_days

formula <- switch(
  dataset,
  "I"  = on_time ~ (1 | customer) + log_amount + quarter + customer_type,
  "II" = on_time ~
    (1 | customer) + log_amount + quarter + payment_term_days + tax
)

logistic_fit <-  glmer(
  formula = formula, data = AR_data, family = binomial(link="logit")
)

# Compute survival model probability of being on time
AR_data$prob_on_time <- NA_real_

for (j in 1:n) AR_data$prob_on_time[j] <-
  sum(prob_payment[1:AR_data$payment_term_days[j], j])

ROC_logistic <- pROC::roc(
  AR_data$on_time, predict(object = logistic_fit, type = "response")
)

print(ROC_logistic)
pdf(file = paste0("ROC_", dataset, ".pdf"), width = 4, height = 4)
par(pty = "s")

plot(
  ROC_logistic, col = "red", xlim = 1:0, ylim = 0:1, legacy.axes = TRUE,
  xlab = "False positive rate", ylab = "True positive rate", xaxs = "i",
  yaxs = "i"
)

print(paste(
  "Brier score:",
  mean((AR_data$on_time - predict(object = logistic_fit, type = "response"))^2)
))

ROC_pred <- pROC::roc(AR_data$on_time, AR_data$prob_on_time)
print(ROC_pred)
plot(ROC_pred, add = TRUE)
print(paste("Brier score:", mean((AR_data$on_time - AR_data$prob_on_time)^2)))

legend(
  x = "bottomright", legend = c("Classification", "Survival model"),
  col = c("red", "black"), lwd = 2
)

dev.off()


## ----------------------------------------------------------------------------
save.image(paste0("RData/workspace_", dataset, ".RData"))
