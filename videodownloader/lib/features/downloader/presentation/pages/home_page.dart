import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/services/injection_container.dart';
import '../../../../core/widgets/app_button.dart';
import '../../../../core/widgets/app_card.dart';
import '../../../../core/widgets/app_text_field.dart';
import '../../../../core/widgets/error_widget.dart';
import '../../../../core/widgets/loading_widget.dart';
import '../cubit/downloader_cubit.dart';
import '../cubit/downloader_state.dart';
import '../widgets/quality_card.dart';
import '../widgets/thumbnail_widget.dart';
import 'package:flutter/services.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final TextEditingController _urlController = TextEditingController();

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _pasteFromClipboard() async {
    final clipboardData = await Clipboard.getData(Clipboard.kTextPlain);
    if (clipboardData != null && clipboardData.text != null) {
      _urlController.text = clipboardData.text!;
    }
  }

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => sl<DownloaderCubit>(),
      child: Scaffold(
        body: Center(
          child: SingleChildScrollView(
            padding: EdgeInsets.symmetric(horizontal: 24.w, vertical: 48.h),
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: 800.w),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // Logo Placeholder
                  Container(
                    width: 80.w,
                    height: 80.w,
                    decoration: BoxDecoration(
                      color: AppColors.primary.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(24.r),
                    ),
                    child: Icon(
                      Icons.download_rounded,
                      color: AppColors.primary,
                      size: 40.w,
                    ),
                  ),
                  SizedBox(height: 24.h),
                  Text(
                    'Video Downloader',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 32.sp,
                      fontWeight: FontWeight.w800,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  SizedBox(height: 12.h),
                  Text(
                    'Download public TikTok and Facebook videos.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 16.sp,
                      fontWeight: FontWeight.w400,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  SizedBox(height: 48.h),
                  AppCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: AppTextField(
                                controller: _urlController,
                                hintText: 'Paste video URL here...',
                                onSubmitted: (value) {
                                  context.read<DownloaderCubit>().downloadVideo(value);
                                },
                              ),
                            ),
                            SizedBox(width: 12.w),
                            IconButton(
                              onPressed: _pasteFromClipboard,
                              tooltip: 'Paste from clipboard',
                              icon: Icon(
                                Icons.content_paste_rounded,
                                color: AppColors.textSecondary,
                                size: 24.w,
                              ),
                            ),
                          ],
                        ),
                        SizedBox(height: 16.h),
                        BlocBuilder<DownloaderCubit, DownloaderState>(
                          builder: (context, state) {
                            return AppButton(
                              text: 'Download',
                              isLoading: state is DownloaderLoading,
                              onPressed: () {
                                context
                                    .read<DownloaderCubit>()
                                    .downloadVideo(_urlController.text);
                              },
                            );
                          },
                        ),
                      ],
                    ),
                  ),
                  SizedBox(height: 32.h),
                  BlocBuilder<DownloaderCubit, DownloaderState>(
                    builder: (context, state) {
                      if (state is DownloaderInitial) {
                        return const SizedBox.shrink();
                      } else if (state is DownloaderLoading) {
                        return const AppCard(
                          child: LoadingWidget(),
                        );
                      } else if (state is DownloaderError) {
                        return AppErrorWidget(
                          message: state.message,
                          onRetry: () {
                            context
                                .read<DownloaderCubit>()
                                .downloadVideo(_urlController.text);
                          },
                        );
                      } else if (state is DownloaderSuccess) {
                        return _buildSuccessState(state);
                      }
                      return const SizedBox.shrink();
                    },
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSuccessState(DownloaderSuccess state) {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ThumbnailWidget(
            url: state.videoDetails.thumbnail,
            platform: state.videoDetails.platform,
            duration: state.videoDetails.duration,
          ),
          SizedBox(height: 16.h),
          Text(
            state.videoDetails.title,
            style: TextStyle(
              fontSize: 18.sp,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
          SizedBox(height: 24.h),
          Text(
            'Available Qualities',
            style: TextStyle(
              fontSize: 14.sp,
              fontWeight: FontWeight.w600,
              color: AppColors.textSecondary,
            ),
          ),
          SizedBox(height: 12.h),
          ...state.videoDetails.qualities.map(
            (q) => QualityCard(
              quality: q,
              pageUrl: _urlController.text.trim(),
              qualityIndex: q.qualityIndex,
              title: state.videoDetails.title,
            ),
          ),
        ],
      ),
    );
  }
}
