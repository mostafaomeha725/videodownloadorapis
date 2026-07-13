import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/app_button.dart';
import '../../domain/downloader_entity.dart';

class QualityCard extends StatelessWidget {
  final VideoQuality quality;
  final String pageUrl;
  final int qualityIndex;
  final String title;

  const QualityCard({
    super.key,
    required this.quality,
    required this.pageUrl,
    required this.qualityIndex,
    required this.title,
  });

  Future<void> _launchDownload() async {
    // Use /download-file so the server (yt-dlp) handles the actual download,
    // bypassing TikTok CDN IP-based token restrictions.
    final downloadUrl = Uri.parse('http://localhost:8000/download-file').replace(
      queryParameters: {
        'page_url': pageUrl,
        'quality_index': qualityIndex.toString(),
        'title': title,
      },
    );
    if (await canLaunchUrl(downloadUrl)) {
      await launchUrl(downloadUrl, mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: EdgeInsets.only(bottom: 12.h),
      padding: EdgeInsets.symmetric(horizontal: 16.w, vertical: 12.h),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(16.r),
        border: Border.all(
          color: AppColors.border,
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Icon(
                Icons.high_quality_rounded,
                color: AppColors.textPrimary,
                size: 24.w,
              ),
              SizedBox(width: 12.w),
              Text(
                quality.quality,
                style: TextStyle(
                  fontSize: 16.sp,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textPrimary,
                ),
              ),
            ],
          ),
          SizedBox(
            width: 120.w,
            child: AppButton(
              text: 'Download',
              onPressed: _launchDownload,
            ),
          ),
        ],
      ),
    );
  }
}
