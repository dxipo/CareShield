# 第三方组件

Gaitkit 通过外部路径调用下列研究代码，不在本目录中重新分发其仓库、模型权重或人体模型文件。

1. [GVHMR](https://github.com/zju3dv/GVHMR) 用于从单目视频恢复带全局方向和平移的 SMPL-X 时间序列。其仓库许可证限定为教育、研究和非营利用途；商业使用须向原作者申请许可。`gaitkit.adapters.gvhmr_headless` 依据其公开演示流程编写，只省略可视化渲染，使用时仍须遵守 GVHMR 的许可证和模型资源条款。

2. [GaitTransformer](https://github.com/IntelligentSensingAndRehabilitation/GaitTransformer) 用于步态相位估计以及 HS、TO 事件解码。其仓库采用 GNU GPL v3，模型权重位于原仓库的 `gait_transformer/assets/model_v0.2.h5`。

3. SMPL-X 人体模型文件由其发布方单独授权。使用者应从官方渠道取得模型文件，并按 GVHMR 文档放置；这些文件不随 Gaitkit 提供。

发表研究结果时，应引用上述项目要求的论文，并在部署前重新核对各组件的最新许可条款。
