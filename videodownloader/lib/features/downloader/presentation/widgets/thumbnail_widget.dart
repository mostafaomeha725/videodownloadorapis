import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import '../../../../core/constants/app_colors.dart';
import '../../../../core/widgets/loading_widget.dart';

class ThumbnailWidget extends StatelessWidget {
  final String url;
  final String platform;
  final String duration;

  const ThumbnailWidget({
    super.key,
    required this.url,
    required this.platform,
    required this.duration,
  });

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16.r),
      child: Stack(
        children: [
          CachedNetworkImage(
            imageUrl: url,
            width: double.infinity,
            height: 200.h,
            fit: BoxFit.cover,
            placeholder: (context, url) => Container(
              color: AppColors.border,
              height: 200.h,
              child: const LoadingWidget(),
            ),
            errorWidget: (context, url, error) => Container(
              color: AppColors.border,
              height: 200.h,
              child: Icon(
                Icons.image_not_supported_rounded,
                color: AppColors.textSecondary,
                size: 40.w,
              ),
            ),
          ),
          Positioned(
            bottom: 12.h,
            right: 12.w,
            child: Container(
              padding: EdgeInsets.symmetric(horizontal: 8.w, vertical: 4.h),
              decoration: BoxDecoration(
                color: Colors.black.withOpacity(0.7),
                borderRadius: BorderRadius.circular(8.r),
              ),
              child: Text(
                duration,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 12.sp,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
          Positioned(
            top: 12.h,
            left: 12.w,
            child: Container(
              padding: EdgeInsets.symmetric(horizontal: 8.w, vertical: 4.h),
              decoration: BoxDecoration(
                color: AppColors.primary,
                borderRadius: BorderRadius.circular(8.r),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    platform.toLowerCase() == 'tiktok'
                        ? Icons.music_note_rounded
                        : Icons.facebook_rounded,
                    color: Colors.white,
                    size: 14.w,
                  ),
                  SizedBox(width: 4.w),
                  Text(
                    platform,
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 12.sp,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
